"""Unit: `FleetDaemon`'s own bookkeeping (ADR-0009) -- independent of a live
delegation. A genuinely in-flight team is simulated with a plain `asyncio.Task`
(no satay, no backend) so "already running" rejection is testable without needing
a real (or even a deliberately-failing) kopicode invocation.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cuttlefish.fleet.daemon import FleetDaemon, FleetError, RunningTeam
from cuttlefish.projects.store import ProjectStore


def _daemon(tmp_path: Path) -> FleetDaemon:
    return FleetDaemon(ProjectStore.open(tmp_path / "projects.db"))


async def _inject_running(daemon: FleetDaemon, project_id: str) -> asyncio.Task[None]:
    """A fake `RunningTeam` whose task never finishes on its own -- the caller
    cancels it once the test no longer needs it running."""

    async def _forever() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(_forever())
    daemon._running[project_id] = RunningTeam(
        team_id="fake-team", base_url="http://127.0.0.1:0", token="fake-token", task=task
    )
    return task


async def test_starting_an_already_running_project_raises_without_touching_it(
    tmp_path: Path,
) -> None:
    daemon = _daemon(tmp_path)
    project = daemon.projects.register(name="alpha", root=str(tmp_path / "alpha"))
    task = await _inject_running(daemon, project.id)

    with pytest.raises(FleetError):
        await daemon.start(project.id, [{"name": "builder", "text": "second attempt"}])

    running = daemon.running(project.id)
    assert running is not None
    assert running.team_id == "fake-team"  # the original, untouched by the rejected call

    task.cancel()


async def test_running_forgets_a_task_once_it_finishes(tmp_path: Path) -> None:
    daemon = _daemon(tmp_path)
    project = daemon.projects.register(name="alpha", root=str(tmp_path / "alpha"))
    task = await _inject_running(daemon, project.id)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert daemon.running(project.id) is None
    assert daemon.is_running(project.id) is False
