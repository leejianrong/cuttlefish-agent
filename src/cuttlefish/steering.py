"""Steering: redirecting a still-running task or team role (ADR-0008).

Round-boundary, not mid-flight — see that ADR for why an in-flight backend
invocation can't be interrupted (no live input channel a headless coding-agent
surface offers, and racing ``satay.wait_for_event`` against an in-flight task via
``satay.gather`` is an unverified composition of satay's own primitives). This
module holds the pieces every side of that design shares: the wire key scheme and
amended-prompt shape ``cuttlefish.workflow``/``cuttlefish.team`` use when polling for
a queued message, and the local pointer file + HTTP client ``cuttlefish.cli``'s
`steer` command uses to actually deliver one. Kept in one place because a mismatch
between how a sender resolves a key and how a workflow's own wait resolves it would
silently misroute a message to nowhere.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

#: How long a delegation round waits, once it ends, for a queued steering message
#: before finalizing with that round's own outcome (ADR-0008) -- long enough that a
#: `cuttlefish steer` call sent right as a round finishes isn't lost to the race,
#: short enough that a round nobody is steering pays a small, bounded tax rather
#: than a real wait.
DEFAULT_STEERING_GRACE_SECONDS = 5.0

#: satay's own wire discriminator for `cuttlefish.episodic.events.SteeringMessage`
#: -- `module.qualname`, exactly what `satay.wait_for_event`/`send_event` derive
#: from the class itself (`satay.api.primitives.event_type_name`). Spelled out as a
#: literal here because `cuttlefish.cli`'s HTTP client sends this same string over
#: the wire without ever importing satay's own primitives.
STEERING_EVENT_TYPE = "cuttlefish.episodic.events.SteeringMessage"


def steering_key(task_id: str, role: str | None) -> str:
    """The satay inbox key one task's (or one team role's) steering channel uses.

    Unscoped for a plain task (there is only one delegation stream to redirect);
    role-scoped for a team, so steering one role never wakes another's poll
    (ADR-0007's own per-role isolation, extended here).
    """
    return task_id if role is None else f"{task_id}:{role}"


def compose_steered_text(
    original_text: str,
    round_summaries: list[str],
    steering_text: str,
    *,
    handover_summary: str | None = None,
) -> str:
    """The next round's task text.

    A fresh backend invocation has no memory of a prior round beyond whatever it
    already wrote to the checkout, so this is the only way it learns either what
    already happened or what the operator just asked for.

    ``handover_summary`` (ADR-0010/KAN-1704) is the most recent
    ``cuttlefish.handover.latest_handover_summary`` for this task/role, or `None`
    if no handover has fired yet. ``round_summaries`` is only ever the raw rounds
    *since* that checkpoint — a caller resets it whenever ``maybe_handover`` just
    fired (``cuttlefish.workflow``/``cuttlefish.team`` both do) — so composed text
    stays bounded across a long steered run instead of re-stating every round
    since the task began, forever, on every single round.
    """
    lines = [original_text, ""]
    if handover_summary is not None:
        lines.append(f"Progress so far (checkpointed summary): {handover_summary}")
    for index, summary in enumerate(round_summaries, start=1):
        lines.append(f"Round {index} since that checkpoint: {summary}")
    lines.append(f"The operator just sent this update -- take it into account: {steering_text}")
    return "\n".join(lines)


def steering_pointer_path(task_id: str) -> Path:
    """Where `cuttlefish run --steerable` publishes `task_id`'s `base_url`/`token`
    for a second CLI invocation (`cuttlefish steer`) to find (ADR-0008) -- one file
    per in-flight steerable task, not a registry service; removed once the run
    reaches a terminal state.
    """
    return Path.cwd() / ".cuttlefish" / "steering" / f"{task_id}.json"


def write_steering_pointer(task_id: str, *, base_url: str, token: str) -> None:
    path = steering_pointer_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"base_url": base_url, "token": token}))


def read_steering_pointer(task_id: str) -> tuple[str, str] | None:
    """`(base_url, token)` for `task_id`, or `None` if it was never steerable, has
    already finished, or its pointer file is otherwise unreadable/malformed."""
    path = steering_pointer_path(task_id)
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    base_url, token = data.get("base_url"), data.get("token")
    if not isinstance(base_url, str) or not isinstance(token, str):
        return None
    return base_url, token


def remove_steering_pointer(task_id: str) -> None:
    steering_pointer_path(task_id).unlink(missing_ok=True)


class SteeringDeliveryError(Exception):
    """`cuttlefish steer` couldn't reach the task, or the task rejected the message."""


def send_steering_message(
    *, base_url: str, token: str, task_id: str, role: str | None, text: str
) -> None:
    """POST one `SteeringMessage` to a running task's control API.

    `POST {base_url}/runs/{task_id}/events` is satay's own control API route
    (ADR-0046) -- the sending side of the wire contract
    `cuttlefish.workflow`/`cuttlefish.team`'s own
    `satay.wait_for_event(SteeringMessage, key=...)` calls receive on the other end.

    A blocking call, by design: `cuttlefish steer` is a short-lived CLI process
    whose only job is this one request, the same synchronous shape `cuttlefish
    secrets get/set` already takes. A caller sharing an event loop with the
    control API it's calling (only possible in-process, e.g. a test) must run
    this off that loop (`asyncio.to_thread`) -- otherwise it deadlocks against
    the very server it's waiting on.
    """
    key = steering_key(task_id, role)
    body = json.dumps(
        {"event_type": STEERING_EVENT_TYPE, "key": key, "payload": {"text": text, "role": role}}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/runs/{task_id}/events",
        data=body,
        method="POST",
        headers={"content-type": "application/json", "x-satay-token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # localhost-only control API
            response.read()
    except urllib.error.HTTPError as exc:
        raise SteeringDeliveryError(f"{base_url} rejected the steering message: {exc}") from exc
    except urllib.error.URLError as exc:
        raise SteeringDeliveryError(f"couldn't reach {base_url}: {exc}") from exc


def cancel_run(*, base_url: str, token: str, run_id: str) -> None:
    """`POST {base_url}/runs/{run_id}/cancel` -- satay's own already-built
    ``ControlAPI.cancel`` route (ADR-0046), reused directly by the fleet daemon
    (ADR-0009) to stop a running team without a subprocess to signal. Cancellation
    still can't interrupt a coding-agent invocation genuinely mid-flight (ADR-0008's
    already-named gap) -- a cancel enqueued while a round is running takes effect at
    that round's own natural end, identically to how a queued `SteeringMessage`
    already does.
    """
    request = urllib.request.Request(
        f"{base_url}/runs/{run_id}/cancel",
        data=b"",
        method="POST",
        headers={"x-satay-token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # localhost-only control API
            response.read()
    except urllib.error.HTTPError as exc:
        raise SteeringDeliveryError(f"{base_url} rejected the cancel: {exc}") from exc
    except urllib.error.URLError as exc:
        raise SteeringDeliveryError(f"couldn't reach {base_url}: {exc}") from exc
