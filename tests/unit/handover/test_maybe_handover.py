from __future__ import annotations

from pathlib import Path

import pytest

from cuttlefish import runtime
from cuttlefish.episodic.events import HandoverWritten, TaskSubmitted
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.handover import maybe_handover
from cuttlefish.llm.provider import LlmResponse
from cuttlefish.llm.replay import ReplayLlmProvider


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    yield
    runtime.reset()


def _configure(tmp_path: Path, *responses: LlmResponse) -> EpisodicStore:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=store,
            llm_provider=ReplayLlmProvider(list(responses)),
            kopicode_binary="kopicode",
        )
    )
    return store


async def test_stays_quiet_under_the_token_budget(tmp_path: Path) -> None:
    store = _configure(tmp_path)
    store.append("task-1", TaskSubmitted(text="a short task"))

    fired = await maybe_handover("task-1", token_budget=10_000)

    assert fired is False
    assert list(store.read("task-1"))[-1].payload == TaskSubmitted(text="a short task")
    store.close()


async def test_fires_once_the_window_crosses_the_budget(tmp_path: Path) -> None:
    store = _configure(tmp_path, LlmResponse(model="replay", text="a distilled summary"))
    store.append("task-1", TaskSubmitted(text="x" * 400))  # ~100 estimated tokens

    fired = await maybe_handover("task-1", token_budget=50)

    assert fired is True
    events = list(store.read("task-1"))
    assert isinstance(events[-1].payload, HandoverWritten)
    assert events[-1].payload.summary == "a distilled summary"
    assert events[-1].payload.covers_seq_from == 1
    assert events[-1].payload.covers_seq_to == 1
    store.close()


async def test_a_second_handover_only_covers_the_window_after_the_first(tmp_path: Path) -> None:
    store = _configure(
        tmp_path,
        LlmResponse(model="replay", text="first summary"),
        LlmResponse(model="replay", text="second summary"),
    )
    store.append("task-1", TaskSubmitted(text="x" * 400))
    assert await maybe_handover("task-1", token_budget=50) is True

    store.append("task-1", TaskSubmitted(text="y" * 400))
    assert await maybe_handover("task-1", token_budget=50) is True

    events = list(store.read("task-1"))
    second_handover = events[-1]
    assert isinstance(second_handover.payload, HandoverWritten)
    assert second_handover.payload.summary == "second summary"
    # Covers only the new TaskSubmitted (seq 3), not the first one already folded
    # into the first handover.
    assert second_handover.payload.covers_seq_from == 3
    assert second_handover.payload.covers_seq_to == 3
    store.close()


async def test_nothing_to_summarise_after_a_handover_is_a_no_op(tmp_path: Path) -> None:
    store = _configure(tmp_path, LlmResponse(model="replay", text="summary"))
    store.append("task-1", TaskSubmitted(text="x" * 400))
    assert await maybe_handover("task-1", token_budget=50) is True

    # Nothing new appended since -- the window is empty, regardless of budget.
    assert await maybe_handover("task-1", token_budget=0) is False
    store.close()
