"""Integration: a real edit landing through the real `claude` binary, live.

The Claude Code counterpart to test_kopicode_live.py's own live proof.
Gated behind ``requires_claude_code_live`` rather than a credential-presence
check: this build's own Claude Code authenticates via an OAuth session with
no ``ANTHROPIC_API_KEY`` set at all (verified live, 2026-09-20), so presence
of a usable credential can't be inferred from the environment the way
kopicode's can — this only runs when an operator deliberately opts in
(``CUTTLEFISH_TEST_CLAUDE_CODE_LIVE=1``), the same cost-bearing discipline
``requires_e2b_credential`` already takes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cuttlefish.delegate.claude_code import run_claude_code


def _init_scratch_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "cuttlefish-tests"], cwd=root, check=True)
    (root / "README.md").write_text("a scratch checkout for a live Claude Code test\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)


@pytest.mark.requires_claude_code_live
async def test_a_real_write_lands_and_is_classified_as_completed(tmp_path: Path) -> None:
    root = tmp_path / "scratch"
    root.mkdir()
    _init_scratch_repo(root)

    outcome = await run_claude_code(
        binary="claude",
        task_text=(
            "Create a file named LIVE_TEST.txt containing the single line: cuttlefish live test"
        ),
        root=str(root),
        timeout=120,
    )

    assert outcome.kind == "completed"
    assert outcome.edited_paths == ["LIVE_TEST.txt"]
    assert (root / "LIVE_TEST.txt").read_text().strip() == "cuttlefish live test"


@pytest.mark.requires_claude_code_live
async def test_no_declared_allowlist_disallows_bash_entirely(tmp_path: Path) -> None:
    root = tmp_path / "scratch"
    root.mkdir()
    _init_scratch_repo(root)

    outcome = await run_claude_code(
        binary="claude",
        task_text="Run the shell command: echo hi > from-bash.txt",
        root=str(root),
        timeout=120,
    )

    # No file landed from a shell command Claude Code was never given a tool
    # to run at all (--disallowedTools Bash) -- a real fail-closed default,
    # not a lesser approximation of kopicode's own (docs/delegate/claude_code
    # .py's module docstring).
    assert outcome.edited_paths == []
    assert not (root / "from-bash.txt").exists()
