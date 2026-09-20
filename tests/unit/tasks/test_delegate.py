"""Unit: delegate_to_agent_backend resolves the runtime's configured backend
and routes to it (ADR-0005) -- the generic wiring, not any one backend's own
mechanics (see tests/unit/agents/ for those).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cuttlefish import runtime
from cuttlefish.agents.outcome import DelegationError
from cuttlefish.agents.registry import UnknownBackendError
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.llm.replay import ReplayLlmProvider
from cuttlefish.tasks.delegate import delegate_to_agent_backend


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    yield
    runtime.reset()


async def test_the_kopicode_backend_is_used_by_default(tmp_path: Path) -> None:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=store,
            llm_provider=ReplayLlmProvider([]),
            kopicode_binary="kopicode-binary-that-does-not-exist",
        )
    )

    with pytest.raises(DelegationError, match="kopicode binary"):
        await delegate_to_agent_backend("add a .gitignore entry", str(tmp_path))

    store.close()


async def test_the_claude_code_backend_is_used_when_configured(tmp_path: Path) -> None:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=store,
            llm_provider=ReplayLlmProvider([]),
            kopicode_binary="kopicode",
            claude_code_binary="claude-binary-that-does-not-exist",
            agent_backend="claude-code",
        )
    )

    with pytest.raises(DelegationError, match="Claude Code binary"):
        await delegate_to_agent_backend("add a .gitignore entry", str(tmp_path))

    store.close()


async def test_an_unknown_configured_backend_raises_rather_than_silently_falling_back(
    tmp_path: Path,
) -> None:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=store,
            llm_provider=ReplayLlmProvider([]),
            kopicode_binary="kopicode",
            agent_backend="not-a-real-backend",
        )
    )

    with pytest.raises(UnknownBackendError):
        await delegate_to_agent_backend("add a .gitignore entry", str(tmp_path))

    store.close()
