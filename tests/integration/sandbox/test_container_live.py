"""Integration: create/exec/snapshot/destroy against a real local Docker daemon
(ADR-0002's 2026-08-26 addendum).

Unlike the E2B backend's live test, this needs no external account or credential
— it self-skips only on a host with no docker on PATH, which GitHub's own
`ubuntu-latest` CI runners already have, so this runs for real in CI too.
"""

from __future__ import annotations

import pytest

from cuttlefish.sandbox import ContainerSandboxProvider, SandboxError, SandboxSpec


@pytest.mark.requires_docker
async def test_create_exec_snapshot_destroy_round_trip() -> None:
    provider = ContainerSandboxProvider()
    handle = await provider.create(SandboxSpec(timeout=120))
    try:
        ok = await provider.exec(handle, ["echo", "hello cuttlefish"])
        assert ok.exit_code == 0
        assert "hello cuttlefish" in ok.stdout

        failing = await provider.exec(handle, ["false"])
        assert failing.exit_code != 0

        cwd_result = await provider.exec(handle, ["pwd"], cwd="/tmp")
        assert cwd_result.stdout.strip() == "/tmp"

        snap = await provider.snapshot(handle)
        assert snap.id
    finally:
        await provider.destroy(handle)


@pytest.mark.requires_docker
async def test_exec_against_a_destroyed_handle_is_a_sandbox_error() -> None:
    provider = ContainerSandboxProvider()
    handle = await provider.create()
    await provider.destroy(handle)

    with pytest.raises(SandboxError):
        await provider.exec(handle, ["echo", "should not run"])


@pytest.mark.requires_docker
async def test_declared_envs_reach_the_container() -> None:
    provider = ContainerSandboxProvider()
    handle = await provider.create(SandboxSpec(envs={"CUTTLEFISH_TEST_VAR": "sandbox-value"}))
    try:
        result = await provider.exec(handle, ["printenv", "CUTTLEFISH_TEST_VAR"])
        assert result.stdout.strip() == "sandbox-value"
    finally:
        await provider.destroy(handle)


@pytest.mark.requires_docker
async def test_destroy_is_idempotent() -> None:
    provider = ContainerSandboxProvider()
    handle = await provider.create()
    await provider.destroy(handle)
    await provider.destroy(handle)
