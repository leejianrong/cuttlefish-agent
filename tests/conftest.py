"""Shared pytest configuration.

Registers satay's own testing fixtures (``ManualClock``, ``SeededRng``,
``FaultInjector``, temp data dirs) as a plugin — the same seam satay-runtime's own
test suite is driven through (docs/PLAN.md "Testing approach").

Also implements the ``requires_kopicode`` marker (declared in pyproject.toml): the
kopicode delegation is tested against kopicode's own headless surface directly,
never a mock, so any test marked with it needs a real ``kopicode`` binary on PATH
and skips itself, rather than fails, when one isn't there — CI's separate
``kopicode-integration`` job builds one; a local ``make test-all`` skips them
quietly.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence

import pytest

pytest_plugins = ["satay.testing.fixtures"]


def pytest_collection_modifyitems(items: Sequence[pytest.Item]) -> None:
    if shutil.which("kopicode") is not None:
        return
    skip = pytest.mark.skip(reason="kopicode is not on PATH (docs/PLAN.md Testing approach)")
    for item in items:
        if item.get_closest_marker("requires_kopicode") is not None:
            item.add_marker(skip)
