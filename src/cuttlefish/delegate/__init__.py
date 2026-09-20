"""The kopicode delegation (ADR-0003): a wrapped invocation of its headless surface.

``DelegationError``/``DelegationOutcome`` are re-exported here for backward
compatibility with code that imported them from this package before they
became backend-agnostic (ADR-0005) — their home is now
``cuttlefish.agents.outcome``.
"""

from __future__ import annotations

from cuttlefish.agents.outcome import DelegationError, DelegationOutcome
from cuttlefish.delegate.kopicode import classify_stream, run_kopicode

__all__ = [
    "DelegationError",
    "DelegationOutcome",
    "classify_stream",
    "run_kopicode",
]
