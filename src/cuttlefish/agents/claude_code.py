"""Headless Claude Code as a second :class:`~cuttlefish.agents.backend.AgentBackend` (ADR-0005).

Proves the pluggable interface generalises past kopicode's own shape.
``cuttlefish.delegate.claude_code``'s own module docstring covers the CLI
mechanics and the honest limits of the policy mapping; this class is the
sandbox-orchestration counterpart to
:class:`~cuttlefish.agents.kopicode.KopicodeBackend`.

**Named credential gap**: this project forwards ``ANTHROPIC_API_KEY`` into a
sandbox, the same mechanism kopicode's own credential uses. That only helps
an operator whose Claude Code is authenticated via an API key. An operator
logged in through Claude Code's own OAuth flow (verified live, 2026-09-20:
this build's own ``claude`` binary authenticates this way, with no
``ANTHROPIC_API_KEY`` set at all) has no session to forward into a fresh
sandbox — a sandboxed :class:`ClaudeCodeBackend` delegation fails closed in
that case. This is a real, accepted gap for this slice (docs/PLAN.md's Open
risks), not a silent one; forwarding an OAuth session into a sandbox is not
attempted here.
"""

from __future__ import annotations

import os
import shutil
from typing import ClassVar

from cuttlefish.agents.outcome import DelegationError, DelegationOutcome
from cuttlefish.delegate.claude_code import run_claude_code, run_claude_code_in_sandbox
from cuttlefish.sandbox.provider import SandboxProvider, SandboxSpec

_SANDBOX_CLAUDE_CODE_BINARY = "/usr/local/bin/claude"

_CREDENTIAL_ENV_VARS = ("ANTHROPIC_API_KEY",)


def _credential_envs() -> dict[str, str]:
    return {name: value for name in _CREDENTIAL_ENV_VARS if (value := os.environ.get(name))}


class ClaudeCodeBackend:
    """Wraps headless Claude Code (``claude -p``) behind the pluggable backend seam."""

    NAME: ClassVar[str] = "claude-code"

    def __init__(self, binary: str = "claude") -> None:
        self._binary = binary

    async def delegate(
        self,
        *,
        task_text: str,
        root: str,
        allow: list[list[str]] | None,
        sandbox_provider: SandboxProvider | None,
    ) -> DelegationOutcome:
        if sandbox_provider is None:
            return await run_claude_code(
                binary=self._binary, task_text=task_text, root=root, allow=allow
            )
        return await self._delegate_inside_sandbox(
            sandbox_provider, task_text=task_text, root=root, allow=allow
        )

    async def _delegate_inside_sandbox(
        self,
        provider: SandboxProvider,
        *,
        task_text: str,
        root: str,
        allow: list[list[str]] | None,
    ) -> DelegationOutcome:
        resolved_binary = shutil.which(self._binary)
        if resolved_binary is None:
            raise DelegationError(f"Claude Code binary {self._binary!r} not found")

        handle = await provider.create(
            SandboxSpec(
                envs=_credential_envs(),
                mounts={resolved_binary: _SANDBOX_CLAUDE_CODE_BINARY, root: root},
            )
        )
        try:
            return await run_claude_code_in_sandbox(
                provider,
                handle,
                binary=_SANDBOX_CLAUDE_CODE_BINARY,
                task_text=task_text,
                root=root,
                allow=allow,
            )
        finally:
            await provider.destroy(handle)
