from __future__ import annotations

from cuttlefish.episodic.events import DelegationFailed, TaskCompleted, TaskSubmitted
from cuttlefish.handover import estimate_event_tokens, estimate_tokens


def test_estimate_tokens_is_roughly_length_over_four() -> None:
    assert estimate_tokens("a" * 40) == 10


def test_estimate_tokens_never_returns_zero_for_nonempty_text() -> None:
    assert estimate_tokens("hi") == 1


def test_estimate_event_tokens_sums_every_text_field() -> None:
    payload = TaskCompleted(result="a" * 40)
    assert estimate_event_tokens(payload) == 10


def test_estimate_event_tokens_zero_for_a_payload_with_no_text_fields() -> None:
    # No such payload exists among the known types today, but decode_payload's
    # UnknownPayload does carry a `data` dict rather than a text field, and
    # estimate_event_tokens must not raise on it.
    from cuttlefish.episodic.events import UnknownPayload

    assert estimate_event_tokens(UnknownPayload(event_type="Future", data={"a": 1})) == 0


def test_delegation_failed_reason_counts() -> None:
    payload = DelegationFailed(reason="b" * 20)
    assert estimate_event_tokens(payload) == 5


def test_task_submitted_text_counts() -> None:
    payload = TaskSubmitted(text="c" * 12)
    assert estimate_event_tokens(payload) == 3
