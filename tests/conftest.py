"""Shared pytest configuration.

Registers satay's own testing fixtures (``ManualClock``, ``SeededRng``,
``FaultInjector``, temp data dirs) as a plugin — the same seam satay-runtime's own
test suite is driven through (docs/PLAN.md "Testing approach").

Also implements the ``requires_kopicode``, ``requires_live_credential``, and
``requires_e2b_credential`` markers (all declared in pyproject.toml): the
kopicode delegation is tested against kopicode's own headless surface directly,
never a mock, so a test needing the real binary or a real model credential
skips itself, rather than fails, when either is missing — CI's separate
``kopicode-integration`` job builds the binary but has no live credential, so
``requires_live_credential`` tests skip there too; both run locally once
``.env`` (or the shell) has a real key. ``requires_e2b_credential`` is never run
in CI at all (docs/SLICES.md V2 test plan, the same cost-bearing posture
kopicode's own ``make bench`` takes) — it only runs locally, and only once an
operator has deliberately set a real ``E2B_API_KEY``.

``load_dotenv()`` runs once here, at collection time, for the same reason
``cli.py`` loads it once at import rather than per call: a test file that only
imports ``cuttlefish.delegate`` never imports ``cli``, so nothing else in the test
session would otherwise load ``.env`` at all.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence

import pytest
from dotenv import load_dotenv

pytest_plugins = ["satay.testing.fixtures"]

load_dotenv()


def pytest_collection_modifyitems(items: Sequence[pytest.Item]) -> None:
    skip_kopicode = pytest.mark.skip(
        reason="kopicode is not on PATH (docs/PLAN.md Testing approach)"
    )
    has_kopicode = shutil.which("kopicode") is not None

    skip_credential = pytest.mark.skip(
        reason="no live OPENROUTER_API_KEY or ANTHROPIC_API_KEY available"
    )
    has_credential = bool(
        os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    )

    skip_e2b = pytest.mark.skip(reason="no live E2B_API_KEY available")
    has_e2b_credential = bool(os.environ.get("E2B_API_KEY"))

    for item in items:
        if not has_kopicode and item.get_closest_marker("requires_kopicode") is not None:
            item.add_marker(skip_kopicode)
        if not has_credential and item.get_closest_marker("requires_live_credential") is not None:
            item.add_marker(skip_credential)
        e2b_marker = item.get_closest_marker("requires_e2b_credential")
        if not has_e2b_credential and e2b_marker is not None:
            item.add_marker(skip_e2b)
