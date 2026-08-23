"""The core task loop: one ``@satay.workflow``, from the first line (ADR-0001).

Slice 1's scope is narrow on purpose (docs/PLAN.md Scope): every task is handed to
kopicode wholesale, with no planning step and no clarifying question back to the
operator (QUESTIONS.md Q18). What this workflow owns is the lifecycle around that one
delegation — journaling what was asked, what was delegated, what came back, and the
terminal state. Everything a person reads back afterward (``cuttlefish show``) is
derived from exactly these events, never a second transcript (ADR-0004).
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import satay

from cuttlefish.delegate.kopicode import DelegationError
from cuttlefish.delegate.policy import DEFAULT_SHELL_ALLOWLIST
from cuttlefish.episodic.events import (
    DelegationCompleted,
    DelegationFailed,
    DelegationRefused,
    DelegationStarted,
    TaskCompleted,
    TaskFailed,
    TaskSubmitted,
)
from cuttlefish.handover import DEFAULT_TOKEN_BUDGET, maybe_handover
from cuttlefish.tasks.delegate import delegate_to_kopicode
from cuttlefish.tasks.journal import journal


class TaskInput(TypedDict):
    """The workflow's input.

    ``task_id`` is filled in by the caller with the *same* id it passes as
    ``satay.start(..., run_id=task_id)`` (QUESTIONS.md Q6: a task's id is the satay
    run id). A workflow body has no other durable way to learn its own run id from
    the inside, so the caller mints one id and uses it both places rather than the
    workflow trying to introspect it — see ``cuttlefish.cli`` for where it's minted.

    ``token_budget`` is optional and defaults to ``handover.DEFAULT_TOKEN_BUDGET``
    — a test lowers it to force a handover deterministically rather than growing a
    real episodic window large enough to cross a realistic one.
    """

    task_id: str
    text: str
    root: str
    token_budget: NotRequired[int]


@satay.workflow
async def run_task(task_input: TaskInput) -> dict[str, Any]:
    task_id = task_input["task_id"]
    text = task_input["text"]
    root = task_input["root"]
    token_budget = task_input.get("token_budget", DEFAULT_TOKEN_BUDGET)

    await journal(task_id, TaskSubmitted(text=text))
    await maybe_handover(task_id, token_budget=token_budget)

    # Every delegation now runs behind kopicode's declared-allowlist policy gate
    # (KAN-987, ADR-0002's addendum) -- this records what was actually declared,
    # not just what was asked.
    await journal(
        task_id,
        DelegationStarted(task_text=text, root=root, policy_allow=DEFAULT_SHELL_ALLOWLIST),
    )

    try:
        outcome = await delegate_to_kopicode(text, root)
    except DelegationError as exc:
        # A plain (non-collected) awaited task's failure re-raises the task body's
        # own exception type unchanged — satay.TaskFailedError only wraps a
        # collect-mode (map/gather return_exceptions=True) failure, which this call
        # isn't (satay's replay/engine.py _execute: `if ... or not
        # _COLLECTING.get(): raise`). So this catches DelegationError itself, not a
        # satay wrapper around it.
        reason = str(exc)
        await journal(task_id, DelegationFailed(reason=reason))
        await maybe_handover(task_id, token_budget=token_budget)
        await journal(task_id, TaskFailed(error=reason))
        return {"status": "failed", "error": reason}

    if outcome.kind == "completed":
        await journal(
            task_id,
            DelegationCompleted(summary=outcome.summary, edited_paths=outcome.edited_paths),
        )
        await maybe_handover(task_id, token_budget=token_budget)
        await journal(task_id, TaskCompleted(result=outcome.summary))
        return {
            "status": "completed",
            "result": outcome.summary,
            "edited_paths": outcome.edited_paths,
        }

    reason = outcome.reason or outcome.summary
    if outcome.kind == "refused":
        await journal(task_id, DelegationRefused(reason=reason))
    else:
        await journal(task_id, DelegationFailed(reason=reason))
    await maybe_handover(task_id, token_budget=token_budget)
    await journal(task_id, TaskFailed(error=reason))
    return {"status": "failed", "error": reason}
