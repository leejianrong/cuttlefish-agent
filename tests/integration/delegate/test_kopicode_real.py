"""Integration tests against the real kopicode binary (docs/PLAN.md "Testing approach").

No mock kopicode. What's exercised here doesn't need a live model credential: a
missing provider API key is itself one of kopicode's real, documented headless
outcomes (`ErrNoAPIKey`, empty stdout, stderr explains why, exit 4) and it's a
genuinely unmocked round trip through the real binary, the real subprocess
plumbing, and cuttlefish's own NDJSON parser. A scenario that needs kopicode to
actually reach a model and get denied or complete a real edit needs a live
provider credential and is out of scope for this suite — see
tests/integration/delegate/test_kopicode_live.py once that's written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cuttlefish.delegate.kopicode import DelegationError, run_kopicode


async def test_missing_binary_raises_delegation_error(tmp_path: Path) -> None:
    # Doesn't need a real kopicode on PATH -- it's testing what happens when the
    # configured binary name doesn't exist at all, so no requires_kopicode marker.
    with pytest.raises(DelegationError, match="not found"):
        await run_kopicode(
            binary="kopicode-binary-that-does-not-exist",
            task_text="add a .gitignore entry",
            root=str(tmp_path),
        )


@pytest.mark.requires_kopicode
async def test_missing_provider_credential_is_a_real_delegation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # kopicode's own documented behaviour with no provider key configured: no
    # session opens at all, so there's nothing for classify_stream to read.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(DelegationError, match=r"no session events|not set"):
        await run_kopicode(
            binary="kopicode",
            task_text="add a .gitignore entry",
            root=str(tmp_path),
        )
