"""Unit: delegate_to_kopicode's own policy-file lifecycle.

Uses a nonexistent binary name so this runs with no real kopicode needed --
DelegationError fires fast (binary not found), but only *after* the policy file
was written and passed, exercising the write-then-cleanup cycle either way.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import cuttlefish.tasks.delegate
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


async def test_a_declared_allowlist_reaches_the_written_policy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KAN-1011: `allow` is forwarded to `write_policy_file`, not silently dropped."""
    store = EpisodicStore.open(tmp_path / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=store,
            llm_provider=ReplayLlmProvider([]),
            kopicode_binary="kopicode-binary-that-does-not-exist",
        )
    )
    captured: dict[str, object] = {}
    original_write_policy_file = cuttlefish.tasks.delegate.write_policy_file

    def spy(path: Path, *, root: str, allow: list[list[str]] | None = None) -> None:
        captured["allow"] = allow
        original_write_policy_file(path, root=root, allow=allow)

    monkeypatch.setattr(cuttlefish.tasks.delegate, "write_policy_file", spy)

    declared = [["go", "test"], ["npm", "test"]]
    with pytest.raises(DelegationError):
        await delegate_to_kopicode("run the tests", str(tmp_path), allow=declared)

    assert captured["allow"] == declared
    store.close()
