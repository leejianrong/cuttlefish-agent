"""Episodic event types: a tagged union, versioned from the first commit (ADR-0004).

Mirrors kopicode's own journal discipline (``internal/journal/event.go``) rather than
rediscovering it: an envelope (schema version, task id, seq, timestamp — see
``cuttlefish.episodic.store``) carries exactly one typed payload, and decoding a
payload whose type this build does not recognise preserves it verbatim
(:class:`UnknownPayload`) instead of dropping it, so an old cuttlefish can still read,
and rewrite, a journal a newer one wrote.

Every payload here is a frozen dataclass with a class-level ``EVENT_TYPE`` constant —
the wire discriminator, matching kopicode's "the payload's type IS the discriminator"
choice so the two never drift apart. :func:`decode_payload` drops any field it doesn't
recognise on a *known* type rather than raising: compatible for readers, not for
rewriters (kopicode's own event.go doc comment states the identical bound), which is a
narrower promise than :class:`UnknownPayload` makes for a whole unrecognised type.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any, ClassVar, cast


@dataclasses.dataclass(frozen=True, slots=True)
class TaskSubmitted:
    """The task text an operator gave cuttlefish, as submitted (PLAN.md R0)."""

    EVENT_TYPE: ClassVar[str] = "TaskSubmitted"

    text: str


@dataclasses.dataclass(frozen=True, slots=True)
class LlmCallCompleted:
    """One of cuttlefish's own reasoning calls (S5's ``LlmProvider`` seam) succeeded."""

    EVENT_TYPE: ClassVar[str] = "LlmCallCompleted"

    model: str
    prompt: str
    response: str
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class LlmCallFailed:
    """One of cuttlefish's own reasoning calls raised rather than returning."""

    EVENT_TYPE: ClassVar[str] = "LlmCallFailed"

    model: str
    prompt: str
    error: str


@dataclasses.dataclass(frozen=True, slots=True)
class DelegationStarted:
    """A coding subtask is about to be handed to kopicode (ADR-0003)."""

    EVENT_TYPE: ClassVar[str] = "DelegationStarted"

    task_text: str
    root: str
    # None before kopicode board KAN-987 landed / when no policy is configured for
    # this invocation — the call runs against kopicode's unconfigured `denyHeadless`
    # default and everything requiring permission is refused. Present once a policy
    # file is written for the call (SLICES.md V1 step 8, ADR-0002's addendum).
    policy_allow: list[list[str]] | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class DelegationCompleted:
    """kopicode finished the delegated subtask and its edits landed."""

    EVENT_TYPE: ClassVar[str] = "DelegationCompleted"

    summary: str
    # A list, not a tuple: JSON has no tuple type, and a decoded event's field must
    # hold exactly what a freshly constructed one does, so the two round-trip
    # identically (dataclasses.asdict re-serialises whatever container is actually
    # there).
    edited_paths: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True, slots=True)
class DelegationRefused:
    """kopicode refused the delegated action — its own permission gate said no.

    Distinct from :class:`DelegationFailed`: a refusal is kopicode's policy (or, before
    KAN-987, its unconditional headless default) declining to act, not an error in the
    call itself (docs/QUESTIONS.md Q16).
    """

    EVENT_TYPE: ClassVar[str] = "DelegationRefused"

    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class DelegationFailed:
    """The delegation call itself failed — a non-zero exit, a malformed NDJSON
    stream, or any other error kopicode did not attribute to a permission decision.
    """

    EVENT_TYPE: ClassVar[str] = "DelegationFailed"

    reason: str


@dataclasses.dataclass(frozen=True, slots=True)
class HandoverWritten:
    """A working-memory handover fired at a token-budget threshold (ADR-0004, Q15).

    ``covers_seq_from``/``covers_seq_to`` point back into the full episodic record
    (inclusive) so anything that later needs the raw window can still find it —
    the handover discards it from live context, never from the journal.
    """

    EVENT_TYPE: ClassVar[str] = "HandoverWritten"

    summary: str
    covers_seq_from: int
    covers_seq_to: int


@dataclasses.dataclass(frozen=True, slots=True)
class TaskCompleted:
    """The task reached a successful terminal state."""

    EVENT_TYPE: ClassVar[str] = "TaskCompleted"

    result: str


@dataclasses.dataclass(frozen=True, slots=True)
class TaskFailed:
    """The task reached a failed terminal state."""

    EVENT_TYPE: ClassVar[str] = "TaskFailed"

    error: str


@dataclasses.dataclass(frozen=True, slots=True)
class UnknownPayload:
    """A payload whose event type this build does not recognise, preserved verbatim.

    ``event_type`` is an instance field here, not a class constant like every other
    payload's ``EVENT_TYPE``: it carries whatever the unrecognised type actually was,
    read back off the wire. Re-encoding it (:func:`encode_payload`) writes ``data``
    back unchanged, so a build that has never heard of a future event type still
    round-trips it losslessly instead of dropping it.
    """

    event_type: str
    data: dict[str, Any]


#: The tagged union. Every payload type an episodic event can carry.
EventPayload = (
    TaskSubmitted
    | LlmCallCompleted
    | LlmCallFailed
    | DelegationStarted
    | DelegationCompleted
    | DelegationRefused
    | DelegationFailed
    | HandoverWritten
    | TaskCompleted
    | TaskFailed
    | UnknownPayload
)

#: Every known (non-:class:`UnknownPayload`) type, keyed by its wire discriminator.
_REGISTRY: Mapping[str, type[Any]] = {
    cls.EVENT_TYPE: cls
    for cls in (
        TaskSubmitted,
        LlmCallCompleted,
        LlmCallFailed,
        DelegationStarted,
        DelegationCompleted,
        DelegationRefused,
        DelegationFailed,
        HandoverWritten,
        TaskCompleted,
        TaskFailed,
    )
}


def encode_payload(payload: EventPayload) -> tuple[str, dict[str, Any]]:
    """The wire discriminator and field dict for `payload`, ready to serialise."""
    if isinstance(payload, UnknownPayload):
        return payload.event_type, dict(payload.data)
    return payload.EVENT_TYPE, dataclasses.asdict(payload)


def decode_payload(event_type: str, data: Mapping[str, Any]) -> EventPayload:
    """The payload `event_type`/`data` decode to.

    An `event_type` this build doesn't recognise decodes to :class:`UnknownPayload`,
    holding `data` verbatim, rather than raising. A recognised type ignores any key in
    `data` it doesn't declare a field for — see the module docstring for why that's
    the correct bound rather than a silent bug.
    """
    cls = _REGISTRY.get(event_type)
    if cls is None:
        return UnknownPayload(event_type=event_type, data=dict(data))
    names = {field.name for field in dataclasses.fields(cls)}
    return cast(
        "EventPayload",
        cls(**{key: value for key, value in data.items() if key in names}),
    )
