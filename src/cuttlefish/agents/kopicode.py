"""kopicode as an :class:`~cuttlefish.agents.backend.AgentBackend` (ADR-0003, ADR-0005).

Everything here already existed in ``cuttlefish.tasks.delegate`` before the
backend became pluggable, moved rather than rewritten:
:meth:`KopicodeBackend.delegate` must behave identically to V1/V2's
``delegate_to_kopicode`` (docs/PLAN.md R1) — same policy file lifecycle, same
sandbox mounts, same credential forwarding.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

from cuttlefish.agents.outcome import DelegationError, DelegationOutcome
from cuttlefish.delegate.kopicode import run_kopicode, run_kopicode_in_sandbox
from cuttlefish.delegate.policy import write_policy_file
from cuttlefish.sandbox.provider import SandboxProvider, SandboxSpec

#: Where the kopicode binary and its policy file land inside a sandbox, fixed
#: rather than mirroring their host paths (cuttlefish.tasks.delegate's
#: original reasoning, unchanged by the move).
_SANDBOX_KOPICODE_BINARY = "/usr/local/bin/kopicode"
_SANDBOX_POLICY_FILE = "/tmp/cuttlefish-policy.toml"  # inside the sandbox, not the host

#: kopicode's own model-provider credential (docs/QUESTIONS.md Q11).
_CREDENTIAL_ENV_VARS = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")


def _credential_envs() -> dict[str, str]:
    return {name: value for name in _CREDENTIAL_ENV_VARS if (value := os.environ.get(name))}


class KopicodeBackend:
    """Wraps ``kopicode run --print`` behind the pluggable backend seam."""

    NAME: ClassVar[str] = "kopicode"

    def __init__(self, binary: str = "kopicode") -> None:
        self._binary = binary

    async def delegate(
        self,
        *,
        task_text: str,
        root: str,
        allow: list[list[str]] | None,
        sandbox_provider: SandboxProvider | None,
    ) -> DelegationOutcome:
        fd, policy_path_str = tempfile.mkstemp(prefix="cuttlefish-policy-", suffix=".toml")
        os.close(fd)
        policy_path = Path(policy_path_str)
        try:
            write_policy_file(policy_path, root=root, allow=allow)
            if sandbox_provider is None:
                return await run_kopicode(
                    binary=self._binary,
                    task_text=task_text,
                    root=root,
                    policy_file=str(policy_path),
                )
            return await self._delegate_inside_sandbox(
                sandbox_provider, task_text=task_text, root=root, policy_path=policy_path
            )
        finally:
            policy_path.unlink(missing_ok=True)

    async def _delegate_inside_sandbox(
        self,
        provider: SandboxProvider,
        *,
        task_text: str,
        root: str,
        policy_path: Path,
    ) -> DelegationOutcome:
        resolved_binary = shutil.which(self._binary)
        if resolved_binary is None:
            raise DelegationError(f"kopicode binary {self._binary!r} not found")

        handle = await provider.create(
            SandboxSpec(
                envs=_credential_envs(),
                mounts={
                    resolved_binary: _SANDBOX_KOPICODE_BINARY,
                    root: root,
                    str(policy_path): _SANDBOX_POLICY_FILE,
                },
            )
        )
        try:
            return await run_kopicode_in_sandbox(
                provider,
                handle,
                binary=_SANDBOX_KOPICODE_BINARY,
                task_text=task_text,
                root=root,
                policy_file=_SANDBOX_POLICY_FILE,
            )
        finally:
            await provider.destroy(handle)
