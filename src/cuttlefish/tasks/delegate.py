"""The coding-agent delegation, wrapped as a satay task (ADR-0001, ADR-0005).

``side_effect=True``: invoking a coding-agent backend genuinely has real-world
effects (it can edit files, and run shell commands once a policy allows it,
ADR-0002's addendum), and satay's own execution guarantees exist precisely to
make a retried side-effecting call safe rather than repeated — see
``cuttlefish.episodic.store``'s module docstring for the one race this
doesn't close.

Which backend actually runs a given call, and whether it runs inside a
sandbox, are both resolved from the process-wide ``runtime.Runtime``
(``cuttlefish.runtime``) at call time, not baked into this task's own
identity. Everything backend-specific — its own policy mechanics, its own
sandbox mounts and credential forwarding — lives on the
:class:`~cuttlefish.agents.backend.AgentBackend` itself
(``cuttlefish.agents``), not here. This replaces V1/V2's kopicode-hardcoded
``delegate_to_kopicode`` (ADR-0005).
"""

from __future__ import annotations

import satay

from cuttlefish import runtime
from cuttlefish.agents.outcome import DelegationOutcome
from cuttlefish.agents.registry import resolve_backend


@satay.task(side_effect=True)
async def delegate_to_agent_backend(
    task_text: str, root: str, allow: list[list[str]] | None = None
) -> DelegationOutcome:
    runtime_ = runtime.current()
    backend = resolve_backend(
        runtime_.agent_backend,
        kopicode_binary=runtime_.kopicode_binary,
        claude_code_binary=runtime_.claude_code_binary,
    )
    return await backend.delegate(
        task_text=task_text,
        root=root,
        allow=allow,
        sandbox_provider=runtime_.sandbox_provider,
    )
