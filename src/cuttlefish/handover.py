"""Working memory: a token-budget check and an automatic handover (ADR-0004, Q15).

Never a hand-maintained document. At a configured token-budget threshold, this
distills the episodic window since the last handover (or the task's start) into
one summary via a single bounded LLM call, and writes the summary back as its own
episodic event (``HandoverWritten``) with a pointer into the full journal — nothing
is dropped from the *record*, only from what a long-running task would otherwise
keep piling into its own live context.
"""

from __future__ import annotations

from cuttlefish.episodic.events import (
    DelegationCompleted,
    DelegationFailed,
    DelegationRefused,
    DelegationStarted,
    EventPayload,
    HandoverWritten,
    LlmCallCompleted,
    LlmCallFailed,
    TaskCompleted,
    TaskFailed,
    TaskSubmitted,
    decode_payload,
)
from cuttlefish.tasks.journal import journal, read_episodic_events
from cuttlefish.tasks.llm import call_llm

#: A placeholder default, not a tuned value — callers configure their own
#: (``cuttlefish.workflow.TaskInput.token_budget``).
DEFAULT_TOKEN_BUDGET = 8_000


def estimate_tokens(text: str) -> int:
    """A rough estimate — ``len(text) // 4`` — never an exact token count.

    cuttlefish links no tokenizer, the same posture kopicode's own
    ``engine.Size.EstimatedTokens`` takes and for the identical reason: every model
    on the roadmap has a different vocabulary, and a byte estimate written as
    though it were exact would be fabricated precision.
    """
    return max(1, len(text) // 4)


def _texts(payload: EventPayload) -> tuple[str, ...]:
    """The free-text field values of `payload` that count toward its token estimate."""
    match payload:
        case TaskSubmitted(text=text):
            return (text,)
        case LlmCallCompleted(prompt=prompt, response=response):
            return (prompt, response)
        case LlmCallFailed(prompt=prompt, error=error):
            return (prompt, error)
        case DelegationStarted(task_text=task_text):
            return (task_text,)
        case DelegationCompleted(summary=summary):
            return (summary,)
        case DelegationRefused(reason=reason) | DelegationFailed(reason=reason):
            return (reason,)
        case HandoverWritten(summary=summary):
            return (summary,)
        case TaskCompleted(result=result):
            return (result,)
        case TaskFailed(error=error):
            return (error,)
        case _:
            return ()


def estimate_event_tokens(payload: EventPayload) -> int:
    return sum(estimate_tokens(text) for text in _texts(payload))


async def maybe_handover(task_id: str, *, token_budget: int = DEFAULT_TOKEN_BUDGET) -> bool:
    """Summarise and checkpoint if the window since the last handover is over budget.

    Reads the full episodic record via the durable ``read_episodic_events`` task
    (never the store directly — see that task's own doc comment for why), finds
    everything after the most recent ``HandoverWritten`` (or the start, if none),
    and — only once that window's estimated size crosses `token_budget` — makes one
    bounded ``call_llm`` call to distill it, then journals the result. Returns
    whether a handover was written, so a caller (mainly a test) can assert it fired.
    """
    raw_events = await read_episodic_events(task_id)
    decoded = [(raw["seq"], decode_payload(raw["event_type"], raw["data"])) for raw in raw_events]

    last_handover_seq = 0
    for seq, payload in decoded:
        if isinstance(payload, HandoverWritten):
            last_handover_seq = seq

    window = [(seq, payload) for seq, payload in decoded if seq > last_handover_seq]
    if not window:
        return False

    total_tokens = sum(estimate_event_tokens(payload) for _, payload in window)
    if total_tokens < token_budget:
        return False

    response = await call_llm(_build_summary_prompt(window))
    text = response["text"]
    summary = text if isinstance(text, str) else str(text)

    await journal(
        task_id,
        HandoverWritten(
            summary=summary,
            covers_seq_from=window[0][0],
            covers_seq_to=window[-1][0],
        ),
    )
    return True


def _build_summary_prompt(window: list[tuple[int, EventPayload]]) -> str:
    lines = [
        "Summarise this task's progress so far in a few sentences, preserving "
        "anything a continuation would need to know.",
        "",
    ]
    for seq, payload in window:
        detail = " | ".join(_texts(payload))
        lines.append(f"{seq}. {type(payload).__name__}: {detail}")
    return "\n".join(lines)
