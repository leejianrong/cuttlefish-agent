"""Unit: cuttlefish.steering's pure helpers and the pointer file (ADR-0008)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cuttlefish.steering import (
    SteeringDeliveryError,
    compose_steered_text,
    read_steering_pointer,
    remove_steering_pointer,
    send_steering_message,
    steering_key,
    steering_pointer_path,
    write_steering_pointer,
)


def test_steering_key_is_unscoped_for_a_plain_task() -> None:
    assert steering_key("task-1", None) == "task-1"


def test_steering_key_is_role_scoped_for_a_team_role() -> None:
    assert steering_key("team-1", "builder") == "team-1:builder"
    assert steering_key("team-1", "reviewer") == "team-1:reviewer"


def test_compose_steered_text_includes_the_original_ask_prior_rounds_and_the_message() -> None:
    text = compose_steered_text(
        "add a .gitignore entry", ["kopicode refused: no policy configured"], "actually try X"
    )
    assert "add a .gitignore entry" in text
    assert "kopicode refused: no policy configured" in text
    assert "actually try X" in text


def test_compose_steered_text_omits_a_handover_line_when_none_has_fired() -> None:
    text = compose_steered_text("add a .gitignore entry", [], "actually try X")
    assert "checkpointed summary" not in text


def test_compose_steered_text_includes_the_handover_summary_when_given_one() -> None:
    """ADR-0010/KAN-1704: the checkpoint `maybe_handover` computes must actually
    reach the next round's own prompt, not stay a write-only journal entry."""
    text = compose_steered_text(
        "add a .gitignore entry",
        [],
        "actually try X",
        handover_summary="rounds 1-3: tried A, then B, both refused",
    )
    assert "rounds 1-3: tried A, then B, both refused" in text
    assert "add a .gitignore entry" in text
    assert "actually try X" in text


def test_pointer_round_trips_through_write_read_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert read_steering_pointer("task-1") is None

    write_steering_pointer("task-1", base_url="http://127.0.0.1:12345", token="secret-token")
    assert steering_pointer_path("task-1").exists()
    assert read_steering_pointer("task-1") == ("http://127.0.0.1:12345", "secret-token")

    remove_steering_pointer("task-1")
    assert read_steering_pointer("task-1") is None


def test_remove_steering_pointer_is_a_noop_when_nothing_is_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    remove_steering_pointer("never-existed")  # must not raise


def test_read_steering_pointer_treats_malformed_json_as_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    path = steering_pointer_path("task-1")
    path.parent.mkdir(parents=True)
    path.write_text("not json")

    assert read_steering_pointer("task-1") is None


def test_send_steering_message_raises_a_delivery_error_when_nothing_is_listening() -> None:
    with pytest.raises(SteeringDeliveryError):
        send_steering_message(
            base_url="http://127.0.0.1:1",  # port 1 -- nothing ever listens there
            token="irrelevant",
            task_id="task-1",
            role=None,
            text="hello",
        )
