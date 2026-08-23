"""Shared pytest configuration.

Registers satay's own testing fixtures (``ManualClock``, ``SeededRng``,
``FaultInjector``, temp data dirs) as a plugin — the same seam satay-runtime's own
test suite is driven through (docs/PLAN.md "Testing approach").
"""

from __future__ import annotations

pytest_plugins = ["satay.testing.fixtures"]
