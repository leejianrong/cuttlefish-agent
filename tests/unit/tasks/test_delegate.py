"""Unit: delegate_to_kopicode's own policy-file lifecycle.

Uses a nonexistent binary name so this runs with no real kopicode needed --
DelegationError fires fast (binary not found), but only *after* the policy file
was written and passed, exercising the write-then-cleanup cycle either way.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cuttlefish import runtime
from cuttlefish.delegate.kopicode import DelegationError
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.llm.replay import ReplayLlmProvider
from cuttlefish.tasks.delegate import delegate_to_kopicode


@pytest.fixture(autouse=True)
def _reset_runtime() -> None:
    yield
    runtime.reset()


async def test_the_temporary_policy_file_is_cleaned_up_after_the_call(
    tmp_path: Path,
) -> None:
    store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=store,
            llm_provider=ReplayLlmProvider([]),
            kopicode_binary="kopicode-binary-that-does-not-exist",
        )
    )
    tmp_dir = Path(tempfile.gettempdir())
    files_before = set(tmp_dir.glob("cuttlefish-policy-*"))

    with pytest.raises(DelegationError):
        await delegate_to_kopicode("add a .gitignore entry", str(tmp_path))

    files_after = set(tmp_dir.glob("cuttlefish-policy-*"))
    assert files_after == files_before
    store.close()
