"""The kopicode delegation, wrapped as a satay task (ADR-0001, ADR-0003).

``side_effect=True``: invoking kopicode genuinely has real-world effects (it can
edit files, and run shell commands once a policy allows it, ADR-0002's addendum),
and satay's own execution guarantees exist precisely to make a retried
side-effecting call safe rather than repeated — see
``cuttlefish.episodic.store``'s module docstring for the one race this doesn't
close.

Every call writes and passes kopicode's declared-allowlist policy file (KAN-987,
``cuttlefish.delegate.policy``) rather than running unconfigured. ``allow`` is
the operator-declared, per-task policy (KAN-1011, docs/SLICES.md V2 step 3) —
``None`` falls back to ``write_policy_file``'s own default, V1's original
hardcoded, no-shell-commands-at-all allowlist.

When ``runtime.current().sandbox_provider`` is configured (docs/SLICES.md V2
step 2, KAN-1010), the call runs inside a sandbox instead of directly on the
host: the scratch checkout, the kopicode binary, and the policy file are all
bind-mounted into it at their own host paths (only a backend that shares the
host filesystem — :class:`~cuttlefish.sandbox.container.ContainerSandboxProvider`
— can do this; a remote backend without local mounts raises
:class:`~cuttlefish.sandbox.provider.SandboxError` from ``create`` itself,
loudly rather than silently running unconfined). No provider configured falls
back to :func:`~cuttlefish.delegate.kopicode.run_kopicode`'s direct host
subprocess, V1's original, still-accepted exception (ADR-0002's addendum).

A sandbox does not inherit the host's environment the way a direct subprocess
does, so kopicode's own model-provider credential is forwarded explicitly
(``_kopicode_credential_envs``) — discovered live: an early sandboxed run
reached kopicode's own "no provider configured" outcome even with a real key
exported on the host, because the container simply never saw it.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import satay

from cuttlefish import runtime
from cuttlefish.delegate.kopicode import (
    DelegationError,
    DelegationOutcome,
    run_kopicode,
    run_kopicode_in_sandbox,
)
from cuttlefish.delegate.policy import write_policy_file
from cuttlefish.sandbox.provider import SandboxProvider, SandboxSpec

#: Where the kopicode binary and its policy file land inside a sandbox, fixed
#: rather than mirroring their host paths — unlike the scratch checkout
#: (mounted at its own path so kopicode's own relative-path behaviour inside it
#: is unaffected), nothing inside the sandbox needs to know where either one
#: happens to live on the host.
_SANDBOX_KOPICODE_BINARY = "/usr/local/bin/kopicode"
_SANDBOX_POLICY_FILE = "/tmp/cuttlefish-policy.toml"  # inside the sandbox, not the host

#: kopicode's own model-provider credential (docs/QUESTIONS.md Q11's
#: OPENROUTER_API_KEY/ANTHROPIC_API_KEY — internal/provider.APIKeyFromEnv reads
#: the ambient process environment, the same two vars this project's own tests
#: already treat as kopicode-relevant). A direct host subprocess inherits the
#: host's environment for free; a sandboxed one runs in its own isolated
#: environment and gets nothing unless it's forwarded explicitly.
_KOPICODE_CREDENTIAL_ENV_VARS = ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")


def _kopicode_credential_envs() -> dict[str, str]:
    return {
        name: value for name in _KOPICODE_CREDENTIAL_ENV_VARS if (value := os.environ.get(name))
    }


@satay.task(side_effect=True)
async def delegate_to_kopicode(
    task_text: str, root: str, allow: list[list[str]] | None = None
) -> DelegationOutcome:
    fd, policy_path_str = tempfile.mkstemp(prefix="cuttlefish-policy-", suffix=".toml")
    os.close(fd)
    policy_path = Path(policy_path_str)
    try:
        write_policy_file(policy_path, root=root, allow=allow)
        runtime_ = runtime.current()
        if runtime_.sandbox_provider is None:
            return await run_kopicode(
                binary=runtime_.kopicode_binary,
                task_text=task_text,
                root=root,
                policy_file=str(policy_path),
            )
        return await _delegate_inside_sandbox(
            runtime_.sandbox_provider,
            binary=runtime_.kopicode_binary,
            task_text=task_text,
            root=root,
            policy_path=policy_path,
        )
    finally:
        policy_path.unlink(missing_ok=True)


async def _delegate_inside_sandbox(
    provider: SandboxProvider,
    *,
    binary: str,
    task_text: str,
    root: str,
    policy_path: Path,
) -> DelegationOutcome:
    resolved_binary = shutil.which(binary)
    if resolved_binary is None:
        raise DelegationError(f"kopicode binary {binary!r} not found")

    handle = await provider.create(
        SandboxSpec(
            envs=_kopicode_credential_envs(),
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
