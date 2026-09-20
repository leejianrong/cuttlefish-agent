"""Integration: `cuttlefish.steering.send_steering_message` actually wakes a parked
`satay.wait_for_event` over real HTTP, through `satay.control.run_app` (ADR-0008,
ADR-0046's control API). The one hop `workflow`/`team`-level tests don't exercise --
those send a `SteeringMessage` directly via `satay.send_event`, in-process; this is
the real second-CLI-invocation path `cuttlefish steer` uses for real.
"""

from __future__ import annotations

import asyncio
from typing import TypedDict

import satay
import satay.control

from cuttlefish.episodic.events import SteeringMessage
from cuttlefish.steering import send_steering_message, steering_key


class _WaitInput(TypedDict):
    task_id: str
    role: str | None


@satay.workflow
async def _wait_for_steering(task_input: _WaitInput) -> str | None:
    message = await satay.wait_for_event(
        SteeringMessage,
        key=steering_key(task_input["task_id"], task_input["role"]),
        timeout=0.3,
    )
    return message.text if message is not None else None


async def test_a_delivered_message_wakes_the_parked_wait_with_its_text() -> None:
    async with satay.control.run_app() as app:
        task_id = "steer-http-hit"
        handle = satay.start(
            _wait_for_steering, {"task_id": task_id, "role": None}, run_id=task_id, store=app.store
        )
        # send_steering_message is a blocking HTTP client, real `cuttlefish steer`
        # is a separate OS process from `cuttlefish run --steerable` -- here both
        # sides share one event loop, so the call must move off it (asyncio.to_thread)
        # or it would deadlock against the uvicorn server that same loop is running.
        await asyncio.to_thread(
            send_steering_message,
            base_url=app.base_url,
            token=app.token,
            task_id=task_id,
            role=None,
            text="hello from the operator",
        )
        result = await handle.result()

    assert result == "hello from the operator"


async def test_a_role_scoped_message_reaches_only_that_roles_key() -> None:
    async with satay.control.run_app() as app:
        task_id = "steer-http-role"
        handle = satay.start(
            _wait_for_steering,
            {"task_id": task_id, "role": "builder"},
            run_id=task_id,
            store=app.store,
        )
        await asyncio.to_thread(
            send_steering_message,
            base_url=app.base_url,
            token=app.token,
            task_id=task_id,
            role="reviewer",
            text="not for you",
        )
        result = await handle.result()

    assert result is None  # builder's own wait timed out -- the message was keyed for reviewer
