"""Unit: the sandboxed invocation path shares its argv-building and output
classification with the direct-host path (`build_kopicode_argv`,
`classify_kopicode_output`) -- this only has to prove the seam between
`run_kopicode_in_sandbox` and a `SandboxProvider`, not kopicode's own event
vocabulary again (already covered by test_kopicode_classify.py).
"""

from __future__ import annotations

import pytest

from cuttlefish.delegate.kopicode import (
    DelegationError,
    build_kopicode_argv,
    run_kopicode_in_sandbox,
)
from cuttlefish.sandbox.provider import ExecResult, SandboxError, SandboxHandle


class _FakeProvider:
    def __init__(self, result: ExecResult | Exception) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    async def exec(
        self,
        handle: SandboxHandle,
        command: list[str],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        self.calls.append({"handle": handle, "command": list(command), "cwd": cwd})
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_build_kopicode_argv_without_policy_file() -> None:
    assert build_kopicode_argv("kopicode", "add a .gitignore entry") == [
        "kopicode",
        "run",
        "--print",
        "add a .gitignore entry",
    ]


def test_build_kopicode_argv_with_policy_file() -> None:
    assert build_kopicode_argv("kopicode", "fix the bug", policy_file="/tmp/policy.toml") == [
        "kopicode",
        "run",
        "--print",
        "--policy-file",
        "/tmp/policy.toml",
        "fix the bug",
    ]


async def test_run_kopicode_in_sandbox_execs_the_right_argv_at_the_right_cwd() -> None:
    session_ended = '{"kind": "session_ended", "exit_code": 0, "reason": "completed"}\n'
    provider = _FakeProvider(ExecResult(exit_code=0, stdout=session_ended, stderr=""))
    handle = SandboxHandle(id="sandbox-1")

    outcome = await run_kopicode_in_sandbox(
        provider,  # type: ignore[arg-type]
        handle,
        binary="/usr/local/bin/kopicode",
        task_text="add a .gitignore entry",
        root="/scratch",
        policy_file="/tmp/policy.toml",
    )

    assert outcome.kind == "completed"
    assert provider.calls == [
        {
            "handle": handle,
            "command": [
                "/usr/local/bin/kopicode",
                "run",
                "--print",
                "--policy-file",
                "/tmp/policy.toml",
                "add a .gitignore entry",
            ],
            "cwd": "/scratch",
        }
    ]


async def test_run_kopicode_in_sandbox_wraps_a_sandbox_error_as_a_delegation_error() -> None:
    provider = _FakeProvider(SandboxError("container gone"))
    handle = SandboxHandle(id="sandbox-1")

    with pytest.raises(DelegationError, match="container gone"):
        await run_kopicode_in_sandbox(
            provider,  # type: ignore[arg-type]
            handle,
            binary="/usr/local/bin/kopicode",
            task_text="add a .gitignore entry",
            root="/scratch",
        )


async def test_run_kopicode_in_sandbox_raises_on_output_with_no_session() -> None:
    provider = _FakeProvider(ExecResult(exit_code=1, stdout="", stderr="boom"))
    handle = SandboxHandle(id="sandbox-1")

    with pytest.raises(DelegationError, match="no session events"):
        await run_kopicode_in_sandbox(
            provider,  # type: ignore[arg-type]
            handle,
            binary="/usr/local/bin/kopicode",
            task_text="add a .gitignore entry",
            root="/scratch",
        )
