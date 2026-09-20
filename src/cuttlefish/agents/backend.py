"""The pluggable coding-agent backend seam (ADR-0005).

Generalises what was kopicode-only through ADR-0003 into a Protocol: any
:class:`AgentBackend` invokes its own tool, parses its own native output into
one :class:`~cuttlefish.agents.outcome.DelegationOutcome`, and owns whatever
policy/sandbox mechanics its own tool actually supports — honestly, not by
pretending to a uniform guarantee no backend can actually promise. See each
backend's own module (``cuttlefish.agents.kopicode``,
``cuttlefish.agents.claude_code``) for what it can and can't do.
"""

from __future__ import annotations

from typing import ClassVar, Protocol

from cuttlefish.agents.outcome import DelegationOutcome
from cuttlefish.sandbox.provider import SandboxProvider


class AgentBackend(Protocol):
    """One coding-agent tool cuttlefish-crew can delegate a task to.

    ``NAME`` is this project's own stable discriminator (mirroring
    :class:`~cuttlefish.sandbox.provider.SandboxProvider.BACKEND_NAME`): the
    episodic journal records which backend actually ran a delegation
    (``DelegationStarted.backend``), and that has to come from somewhere
    stable, not a Python class name a refactor could quietly change.
    """

    NAME: ClassVar[str]

    async def delegate(
        self,
        *,
        task_text: str,
        root: str,
        allow: list[list[str]] | None,
        sandbox_provider: SandboxProvider | None,
    ) -> DelegationOutcome: ...
