"""Integration-tier fixtures.

The kopicode delegation is tested against kopicode's own headless surface directly
(docs/PLAN.md "Testing approach"), never a mock. Those tests need a real ``kopicode``
binary on PATH and skip themselves when it's absent, rather than fail — CI's separate
``kopicode-integration`` job builds and provides one; a local ``make test-all`` skips
them quietly when the binary isn't installed.
"""

from __future__ import annotations

import shutil

import pytest

requires_kopicode = pytest.mark.skipif(
    shutil.which("kopicode") is None,
    reason="kopicode is not on PATH (docs/PLAN.md Testing approach)",
)
