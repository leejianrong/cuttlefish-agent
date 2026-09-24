from __future__ import annotations

from pathlib import Path

import pytest

from cuttlefish import runtime
from cuttlefish.episodic.events import HandoverWritten, TaskSubmitted
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.handover import latest_handover_summary, maybe_handover
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


async def test_role_filters_the_window_to_that_roles_own_events(tmp_path: Path) -> None:
    """ADR-0007: a team shares one task_id, so a role's own handover must not see,
    or be triggered by, another role's events."""
    store = _configure(tmp_path, LlmResponse(model="replay", text="builder summary"))
    store.append("team-1", TaskSubmitted(text="x" * 4000, role="builder"))
    store.append("team-1", TaskSubmitted(text="y" * 4000, role="reviewer"))

    fired = await maybe_handover("team-1", token_budget=50, role="builder")

    assert fired is True
    events = list(store.read("team-1"))
    handovers = [e for e in events if isinstance(e.payload, HandoverWritten)]
    assert len(handovers) == 1
    assert handovers[0].payload.role == "builder"
    assert handovers[0].payload.covers_seq_from == 1
    assert handovers[0].payload.covers_seq_to == 1  # the reviewer's own event (seq 2) excluded
    store.close()


async def test_one_roles_handover_does_not_suppress_anothers(tmp_path: Path) -> None:
    store = _configure(
        tmp_path,
        LlmResponse(model="replay", text="builder summary"),
        LlmResponse(model="replay", text="reviewer summary"),
    )
    store.append("team-1", TaskSubmitted(text="x" * 4000, role="builder"))
    store.append("team-1", TaskSubmitted(text="y" * 4000, role="reviewer"))
    assert await maybe_handover("team-1", token_budget=50, role="builder") is True

    # The reviewer's own window is untouched by the builder's handover above.
    assert await maybe_handover("team-1", token_budget=50, role="reviewer") is True

    events = list(store.read("team-1"))
    handovers = [e for e in events if isinstance(e.payload, HandoverWritten)]
    assert {h.payload.role for h in handovers} == {"builder", "reviewer"}
    store.close()


async def test_role_none_stays_the_plain_single_task_behaviour(tmp_path: Path) -> None:
    """A role-tagged event must not leak into the default (role=None) window --
    otherwise a plain `cuttlefish run` sharing a store with a team elsewhere would
    see its own budget consumed by events that aren't its own."""
    store = _configure(tmp_path)
    store.append("task-1", TaskSubmitted(text="x" * 4000, role="builder"))

    fired = await maybe_handover("task-1", token_budget=50)

    assert fired is False
    store.close()


# -- latest_handover_summary (ADR-0010/KAN-1704) --------------------------------


async def test_latest_handover_summary_is_none_before_any_handover_fires(tmp_path: Path) -> None:
    store = _configure(tmp_path)
    store.append("task-1", TaskSubmitted(text="a short task"))

    assert await latest_handover_summary("task-1") is None
    store.close()


async def test_latest_handover_summary_returns_the_most_recent_one(tmp_path: Path) -> None:
    store = _configure(
        tmp_path,
        LlmResponse(model="replay", text="first summary"),
        LlmResponse(model="replay", text="second summary"),
    )
    store.append("task-1", TaskSubmitted(text="x" * 400))
    assert await maybe_handover("task-1", token_budget=50) is True
    assert await latest_handover_summary("task-1") == "first summary"

    store.append("task-1", TaskSubmitted(text="y" * 400))
    assert await maybe_handover("task-1", token_budget=50) is True
    assert await latest_handover_summary("task-1") == "second summary"
    store.close()


async def test_latest_handover_summary_is_role_scoped(tmp_path: Path) -> None:
    """The identical role filter `maybe_handover` itself uses (ADR-0007) -- a
    caller reading back one role's own checkpoint must never see another role's."""
    store = _configure(
        tmp_path,
        LlmResponse(model="replay", text="builder summary"),
    )
    store.append("team-1", TaskSubmitted(text="x" * 4000, role="builder"))
    assert await maybe_handover("team-1", token_budget=50, role="builder") is True

    assert await latest_handover_summary("team-1", role="builder") == "builder summary"
    assert await latest_handover_summary("team-1", role="reviewer") is None
    assert await latest_handover_summary("team-1") is None  # role=None is its own lane too
    store.close()
