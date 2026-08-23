"""The kopicode delegation (ADR-0003): a wrapped invocation of its headless surface."""

from __future__ import annotations

from cuttlefish.delegate.kopicode import (
    DelegationError,
    DelegationOutcome,
    classify_stream,
    run_kopicode,
)

__all__ = [
    "DelegationError",
    "DelegationOutcome",
    "classify_stream",
    "run_kopicode",
]
