"""Integration: create/exec/snapshot/destroy against a real E2B account (ADR-0002).

docs/SLICES.md V2 test plan: "exercised against a real E2B account in CI, gated
behind a cost-bearing test tag the same way kopicode gates its own paid
`make bench`." This project doesn't wire a paid job into CI on a guess about
what it should assert before there's real usage to build it against (the same
restraint ADR-0002 itself argues for) — the marker exists so this test is ready
to run, locally, once an operator sets a real E2B_API_KEY (`make
test-sandbox-live`); it never runs in CI at all.
"""

from __future__ import annotations

import pytest

from cuttlefish.sandbox import E2bSandboxProvider, SandboxSpec


@pytest.mark.requires_e2b_credential
async def test_create_exec_snapshot_destroy_round_trip() -> None:
    provider = E2bSandboxProvider()
    handle = await provider.create(SandboxSpec(timeout=60))
    try:
        ok = await provider.exec(handle, ["echo", "hello cuttlefish"])
        assert ok.exit_code == 0
        assert "hello cuttlefish" in ok.stdout

        failing = await provider.exec(handle, ["false"])
        assert failing.exit_code != 0

        snap = await provider.snapshot(handle)
        assert snap.id
    finally:
        await provider.destroy(handle)
