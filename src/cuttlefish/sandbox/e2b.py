"""The E2B-backed ``SandboxProvider`` (ADR-0002) — the only backend this project
builds, per that ADR's decision not to compete with an already-consolidating
market of sandbox providers.

Every method re-``connect``s the handle's id into a live ``e2b.AsyncSandbox``
before acting on it, rather than holding one open across calls: e2b sandboxes are
addressed by id across process boundaries by design, and this provider has no
fork-and-replay usage yet (ADR-0002) that would justify caching a live
connection instead.
"""

from __future__ import annotations

import os
import shlex
from collections.abc import Sequence
from typing import Protocol

from e2b import AsyncSandbox, CommandExitException
from e2b.exceptions import AuthenticationException, SandboxException

from cuttlefish.sandbox.provider import (
    ExecResult,
    SandboxError,
    SandboxHandle,
    SandboxSpec,
    SnapshotHandle,
)

E2B_API_KEY_ENV = "E2B_API_KEY"

#: e2b's own exception hierarchy is split: most failures are `SandboxException`,
#: but a bad credential raises `AuthenticationException`, which does not inherit
#: from it — both are backend failures from this module's point of view.
_E2B_ERRORS = (SandboxException, AuthenticationException)


class MissingApiKeyError(RuntimeError):
    """`E2B_API_KEY` isn't set (checked before the first call, not mid-task)."""


class _CommandResultLike(Protocol):
    """The subset of `e2b.CommandResult` (and `e2b.CommandExitException`, which
    carries the same fields for a non-zero exit) this module reads."""

    stdout: str
    stderr: str
    exit_code: int


class E2bSandboxProvider:
    """`SandboxProvider` over E2B's `AsyncSandbox` client."""

    def __init__(self, *, api_key: str | None = None, template: str | None = None) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get(E2B_API_KEY_ENV)
        if not resolved_key:
            raise MissingApiKeyError(f"{E2B_API_KEY_ENV} is not set")
        self._api_key = resolved_key
        self._template = template

    async def create(self, spec: SandboxSpec | None = None) -> SandboxHandle:
        resolved_spec = spec if spec is not None else SandboxSpec()
        try:
            sandbox = await AsyncSandbox.create(
                template=resolved_spec.template or self._template,
                timeout=int(resolved_spec.timeout) if resolved_spec.timeout is not None else None,
                envs=dict(resolved_spec.envs) or None,
                api_key=self._api_key,
            )
        except _E2B_ERRORS as exc:
            raise SandboxError(f"e2b sandbox create failed: {exc}") from exc
        return SandboxHandle(id=sandbox.sandbox_id)

    async def exec(
        self,
        handle: SandboxHandle,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        sandbox = await self._connect(handle)
        try:
            result: _CommandResultLike = await sandbox.commands.run(
                shlex.join(command), cwd=cwd, timeout=timeout
            )
        except CommandExitException as exc:
            # A non-zero exit is a real, reportable result, not this module's own
            # error — the caller reads `ExecResult.exit_code`, the same way
            # `subprocess.run` does not raise for a failing command. Checked before
            # `_E2B_ERRORS` below, which `CommandExitException` also happens to
            # subclass.
            result = exc
        except _E2B_ERRORS as exc:
            raise SandboxError(f"e2b exec failed in sandbox {handle.id!r}: {exc}") from exc
        return _to_exec_result(result)

    async def snapshot(self, handle: SandboxHandle) -> SnapshotHandle:
        sandbox = await self._connect(handle)
        try:
            info = await sandbox.create_snapshot()
        except _E2B_ERRORS as exc:
            raise SandboxError(f"e2b snapshot failed for sandbox {handle.id!r}: {exc}") from exc
        return SnapshotHandle(id=info.snapshot_id)

    async def destroy(self, handle: SandboxHandle) -> None:
        sandbox = await self._connect(handle)
        try:
            await sandbox.kill()
        except _E2B_ERRORS as exc:
            raise SandboxError(f"e2b destroy failed for sandbox {handle.id!r}: {exc}") from exc

    async def _connect(self, handle: SandboxHandle) -> AsyncSandbox:
        try:
            return await AsyncSandbox.connect(handle.id, api_key=self._api_key)
        except _E2B_ERRORS as exc:
            raise SandboxError(f"e2b sandbox {handle.id!r} not found: {exc}") from exc


def _to_exec_result(result: _CommandResultLike) -> ExecResult:
    return ExecResult(exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr)
