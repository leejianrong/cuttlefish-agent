"""The ``SandboxProvider`` seam for real process/container containment (ADR-0002, Q12).

Not wired into the kopicode delegation yet — that is V2 step 2
(``docs/SLICES.md``, KAN-1010). This module is the interface itself: create,
exec, snapshot, destroy, loosely matching the shape OpenAI's Agents SDK already
standardised across seven sandbox providers, so this project is compatible with
an emerging convention rather than inventing its own (QUESTIONS.md Q12).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SandboxHandle:
    """One live sandbox, opaque past its own id — a provider's own concern."""

    id: str


@dataclass(frozen=True, slots=True)
class ExecResult:
    """One completed ``exec`` call. A non-zero ``exit_code`` is not an error here —
    the caller decides what a given command's failure means, the same way
    ``subprocess.run`` reports it rather than raising."""

    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class SnapshotHandle:
    """A named, resumable capture of a sandbox's filesystem state at one point in
    time. Restoring one into a new sandbox is not part of this interface yet —
    ADR-0002 defers that (a snapshot tied to a satay journal turn) to a fresh ADR
    once there is real fork-and-replay usage to build it against."""

    id: str


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """What ``create`` asks a provider to start, kept separate from the handle it
    returns so a caller's request and a provider's own bookkeeping never share one
    type."""

    template: str | None = None
    timeout: float | None = None
    envs: Mapping[str, str] = field(default_factory=dict)


class SandboxError(Exception):
    """A sandbox operation couldn't be completed — the provider's own backend
    rejected it, or the handle it was given no longer refers to anything live."""


class SandboxProvider(Protocol):
    """A cuttlefish-facing sandbox provider: create, exec, snapshot, destroy.

    E2B is the only backend this project builds (ADR-0002's decision) — this
    Protocol exists so the kopicode delegation (V2 step 2) depends on this shape,
    not on E2B's own client directly.
    """

    async def create(self, spec: SandboxSpec | None = None) -> SandboxHandle: ...

    async def exec(
        self,
        handle: SandboxHandle,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> ExecResult: ...

    async def snapshot(self, handle: SandboxHandle) -> SnapshotHandle: ...

    async def destroy(self, handle: SandboxHandle) -> None: ...
