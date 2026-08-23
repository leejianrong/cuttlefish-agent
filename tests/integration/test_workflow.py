"""Integration: the real @satay.workflow, the real episodic journal, the real kopicode.

No mock kopicode (docs/PLAN.md "Testing approach"). The provider credential is
deliberately unset so the run reaches kopicode's own real "no provider configured"
outcome rather than a live model call — see
tests/integration/delegate/test_kopicode_real.py for why that's still a genuine,
unmocked round trip and not a stand-in for one. What this test actually exercises is
the mechanism build plan steps 2-4 assembled: the workflow drives the real
delegation task, which shells out to the real binary, and the failure it hits is
journaled as real episodic events — nothing here is faked except the one thing this
suite has no live credential for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from satay.api.primitives import start
from satay.journal.store import SQLiteStore

from cuttlefish import runtime
from cuttlefish.episodic.events import DelegationFailed, TaskFailed, TaskSubmitted
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.llm.replay import ReplayLlmProvider
from cuttlefish.workflow import run_task


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    yield
    runtime.reset()


@pytest.mark.requires_kopicode
async def test_a_refused_delegation_is_a_journaled_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    episodic_store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=episodic_store,
            llm_provider=ReplayLlmProvider([]),
            kopicode_binary="kopicode",
        )
    )
    satay_store = SQLiteStore.open(":memory:")
    task_id = "test-task-1"
    root = tmp_path / "scratch"
    root.mkdir()

    handle = start(
        run_task,
        {"task_id": task_id, "text": "add a .gitignore entry", "root": str(root)},
        run_id=task_id,
        store=satay_store,
    )
    result = await handle.result()

    assert result["status"] == "failed"
    assert "error" in result

    events = list(episodic_store.read(task_id))
    kinds = [type(event.payload).__name__ for event in events]
    assert kinds == ["TaskSubmitted", "DelegationFailed", "TaskFailed"]
    assert isinstance(events[0].payload, TaskSubmitted)
    assert events[0].payload.text == "add a .gitignore entry"
    assert isinstance(events[1].payload, DelegationFailed)
    assert isinstance(events[2].payload, TaskFailed)

    episodic_store.close()
    satay_store.close()
