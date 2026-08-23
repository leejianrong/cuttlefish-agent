"""Integration tier: the episodic store against a real on-disk SQLite file.

docs/SLICES.md V1 integration test plan: "A secret value (a fake API key) placed in
a tool result is absent from the written episodic journal file, byte for byte."
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from cuttlefish.episodic.events import (
    DelegationCompleted,
    LlmCallCompleted,
    TaskCompleted,
    TaskSubmitted,
    UnknownPayload,
)
from cuttlefish.episodic.redact import Redactor
from cuttlefish.episodic.store import EpisodicStore


def _lookup(values: dict[str, str]) -> Callable[[str], str | None]:
    return values.get


def test_events_round_trip_in_seq_order(tmp_path: Path) -> None:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    try:
        store.append("task-1", TaskSubmitted(text="add a .gitignore entry"))
        store.append("task-1", LlmCallCompleted(model="claude", prompt="hi", response="ok"))
        store.append("task-1", TaskCompleted(result="done"))

        events = list(store.read("task-1"))
    finally:
        store.close()

    assert [event.seq for event in events] == [1, 2, 3]
    assert events[0].payload == TaskSubmitted(text="add a .gitignore entry")
    assert events[2].payload == TaskCompleted(result="done")


def test_two_tasks_keep_independent_seq_counters(tmp_path: Path) -> None:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    try:
        store.append("task-a", TaskSubmitted(text="task a"))
        store.append("task-b", TaskSubmitted(text="task b"))
        store.append("task-a", TaskCompleted(result="done a"))

        task_a_events = list(store.read("task-a"))
        task_b_events = list(store.read("task-b"))
    finally:
        store.close()

    assert [event.seq for event in task_a_events] == [1, 2]
    assert [event.seq for event in task_b_events] == [1]


def test_reopening_the_same_file_continues_the_seq_counter(tmp_path: Path) -> None:
    path = tmp_path / "episodic.db"
    store = EpisodicStore.open(path)
    store.append("task-1", TaskSubmitted(text="first"))
    store.close()

    reopened = EpisodicStore.open(path)
    try:
        reopened.append("task-1", TaskCompleted(result="done"))
        events = list(reopened.read("task-1"))
    finally:
        reopened.close()

    assert [event.seq for event in events] == [1, 2]


def test_secret_is_absent_from_the_journal_file_byte_for_byte(tmp_path: Path) -> None:
    path = tmp_path / "episodic.db"
    secret = "sk-ant-fake-0123456789abcdef"
    redactor = Redactor(["ANTHROPIC_API_KEY"], lookup=_lookup({"ANTHROPIC_API_KEY": secret}))
    store = EpisodicStore.open(path, redactor=redactor)
    try:
        store.append(
            "task-1",
            DelegationCompleted(
                summary=f"ran `env`, saw ANTHROPIC_API_KEY={secret} in the output",
            ),
        )
    finally:
        store.close()

    raw_bytes = path.read_bytes()
    assert secret.encode() not in raw_bytes

    # And what's actually readable back reflects the redaction, not the original.
    store = EpisodicStore.open(path)
    try:
        (event,) = list(store.read("task-1"))
    finally:
        store.close()
    assert isinstance(event.payload, DelegationCompleted)
    assert secret not in event.payload.summary
    assert "[redacted:ANTHROPIC_API_KEY]" in event.payload.summary


def test_an_event_type_this_build_does_not_know_survives_a_read(tmp_path: Path) -> None:
    # Simulates a journal written by a future build with a payload type this one has
    # never heard of (ADR-0004: "an unmarshaller that preserves an event type it
    # doesn't recognise rather than dropping it").
    path = tmp_path / "episodic.db"
    store = EpisodicStore.open(path)
    store.close()

    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO episodic_events "
        "(task_id, seq, schema_version, event_type, ts, payload_json) "
        "VALUES ('task-1', 1, 1, 'SomeFutureEvent', '2026-08-23T00:00:00+00:00', "
        '\'{"shape": "unknown"}\')'
    )
    connection.commit()
    connection.close()

    reopened = EpisodicStore.open(path)
    try:
        (event,) = list(reopened.read("task-1"))
    finally:
        reopened.close()

    assert isinstance(event.payload, UnknownPayload)
    assert event.payload.event_type == "SomeFutureEvent"
    assert event.payload.data == {"shape": "unknown"}
