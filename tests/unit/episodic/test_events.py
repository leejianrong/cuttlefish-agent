from __future__ import annotations

import dataclasses

import pytest

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
    UnknownPayload,
    decode_payload,
    encode_payload,
)

KNOWN_PAYLOADS: list[EventPayload] = [
    TaskSubmitted(text="add a .gitignore entry for build artifacts"),
    LlmCallCompleted(
        model="claude", prompt="hi", response="hello", input_tokens=3, output_tokens=1
    ),
    LlmCallCompleted(model="claude", prompt="hi", response="hello"),
    LlmCallFailed(model="claude", prompt="hi", error="rate limited"),
    DelegationStarted(task_text="fix the bug", root="/tmp/scratch"),
    DelegationStarted(task_text="fix the bug", root="/tmp/scratch", policy_allow=[["go", "test"]]),
    DelegationCompleted(summary="added the entry", edited_paths=[".gitignore"]),
    DelegationRefused(reason="run_shell is not on the declared allowlist"),
    DelegationFailed(reason="kopicode binary exited 1"),
    HandoverWritten(summary="working on the gitignore task", covers_seq_from=1, covers_seq_to=8),
    TaskCompleted(result="done"),
    TaskFailed(error="delegation refused"),
]


@pytest.mark.parametrize("payload", KNOWN_PAYLOADS)
def test_known_payload_round_trips(payload: EventPayload) -> None:
    event_type, data = encode_payload(payload)
    assert event_type == payload.EVENT_TYPE  # type: ignore[union-attr]
    decoded = decode_payload(event_type, data)
    assert decoded == payload


def test_unrecognised_event_type_becomes_unknown_payload() -> None:
    decoded = decode_payload("SomeFutureEvent", {"whatever": "shape", "n": 3})
    assert isinstance(decoded, UnknownPayload)
    assert decoded.event_type == "SomeFutureEvent"
    assert decoded.data == {"whatever": "shape", "n": 3}


def test_unknown_payload_round_trips_verbatim() -> None:
    original = UnknownPayload(event_type="SomeFutureEvent", data={"whatever": "shape"})
    event_type, data = encode_payload(original)
    assert event_type == "SomeFutureEvent"
    assert data == {"whatever": "shape"}
    decoded = decode_payload(event_type, data)
    assert decoded == original


def test_decode_ignores_a_field_a_known_type_does_not_declare() -> None:
    # A newer build added a field this one has never heard of. Decoding must not
    # raise -- "compatible for readers, not for rewriters" (events.py docstring).
    data = dataclasses.asdict(TaskSubmitted(text="hello")) | {"future_field": "value"}
    decoded = decode_payload("TaskSubmitted", data)
    assert decoded == TaskSubmitted(text="hello")
