"""The pluggable coding-agent backend seam (ADR-0005).

Kept deliberately small: importing this package must never import
``cuttlefish.delegate`` transitively (``cuttlefish.delegate.kopicode``
imports :class:`DelegationOutcome`/:class:`DelegationError` from here), so
only names with no dependency back on a specific backend's own mechanics are
re-exported at this level. ``KopicodeBackend``, ``ClaudeCodeBackend``, and
``resolve_backend`` live in their own submodules — import them from there
(``cuttlefish.agents.kopicode``, ``cuttlefish.agents.claude_code``,
``cuttlefish.agents.registry``).
"""

from __future__ import annotations

from cuttlefish.agents.backend import AgentBackend
from cuttlefish.agents.outcome import DelegationError, DelegationOutcome

__all__ = ["AgentBackend", "DelegationError", "DelegationOutcome"]
