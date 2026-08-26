"""A container-backed ``SandboxProvider`` (ADR-0002's 2026-08-26 addendum): real
process/container containment via a local Docker daemon, needing no external
account or credential — unlike :class:`~cuttlefish.sandbox.e2b.E2bSandboxProvider`,
usable the moment a task needs real containment.

Shells out to the ``docker`` CLI directly, the same posture this project already
takes toward kopicode (ADR-0003) rather than adding a client SDK: one external
binary, invoked as-is, no new protocol of this project's own.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Sequence

from cuttlefish.sandbox.provider import (
    ExecResult,
    SandboxError,
    SandboxHandle,
    SandboxSpec,
    SnapshotHandle,
)

DEFAULT_IMAGE = "debian:bookworm-slim"
DEFAULT_DOCKER_BINARY = "docker"

#: docker's own stderr wording when a container id no longer refers to anything
#: live — distinguishes "this handle is stale" (a SandboxError) from "the
#: command we ran inside the container failed" (a normal, reportable ExecResult).
_NO_SUCH_CONTAINER = "No such container"


class DockerNotAvailableError(RuntimeError):
    """``docker`` isn't on PATH (checked before the first call, not mid-task)."""


class ContainerSandboxProvider:
    """``SandboxProvider`` over a local Docker daemon, via the ``docker`` CLI.

    Every sandbox is one detached container running ``sleep`` for `timeout`
    seconds (or indefinitely, with none declared) — a real process to `exec`
    into, and a hard lifetime matching E2B's own `timeout` semantics (a sandbox
    TTL, not an idle timeout) rather than a new concept of this module's own.
    """

    def __init__(
        self, *, image: str | None = None, docker_binary: str = DEFAULT_DOCKER_BINARY
    ) -> None:
        if shutil.which(docker_binary) is None:
            raise DockerNotAvailableError(f"{docker_binary!r} is not on PATH")
        self._image = image or DEFAULT_IMAGE
        self._docker_binary = docker_binary

    async def create(self, spec: SandboxSpec | None = None) -> SandboxHandle:
        resolved_spec = spec if spec is not None else SandboxSpec()
        sleep_for = (
            str(int(resolved_spec.timeout)) if resolved_spec.timeout is not None else "infinity"
        )
        args = ["run", "-d"]
        for key, value in resolved_spec.envs.items():
            args += ["-e", f"{key}={value}"]
        args += [resolved_spec.template or self._image, "sleep", sleep_for]

        code, stdout, stderr = await self._docker(*args)
        if code != 0:
            raise SandboxError(f"docker run failed: {stderr.strip()}")
        return SandboxHandle(id=stdout.strip())

    async def exec(
        self,
        handle: SandboxHandle,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult:
        args = ["exec"]
        if cwd is not None:
            args += ["-w", cwd]
        args += [handle.id, *command]

        code, stdout, stderr = await self._docker(*args, timeout=timeout)
        if code != 0 and _NO_SUCH_CONTAINER in stderr:
            raise SandboxError(f"container {handle.id!r} not found: {stderr.strip()}")
        return ExecResult(exit_code=code, stdout=stdout, stderr=stderr)

    async def snapshot(self, handle: SandboxHandle) -> SnapshotHandle:
        code, stdout, stderr = await self._docker("commit", handle.id)
        if code != 0:
            raise SandboxError(f"docker commit failed for {handle.id!r}: {stderr.strip()}")
        return SnapshotHandle(id=stdout.strip())

    async def destroy(self, handle: SandboxHandle) -> None:
        code, _stdout, stderr = await self._docker("rm", "-f", handle.id)
        if code != 0 and _NO_SUCH_CONTAINER not in stderr:
            raise SandboxError(f"docker rm failed for {handle.id!r}: {stderr.strip()}")

    async def _docker(self, *args: str, timeout: float | None = None) -> tuple[int, str, str]:
        process = await asyncio.create_subprocess_exec(
            self._docker_binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise SandboxError(f"docker {args[0]} timed out after {timeout}s") from exc
        assert process.returncode is not None
        return (
            process.returncode,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
        )
