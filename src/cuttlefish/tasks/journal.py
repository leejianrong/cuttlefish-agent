"""The episodic-journal-append satay task (ADR-0001, ADR-0004).

Every episodic write goes through this one task rather than calling
``EpisodicStore.append`` directly from a workflow body: a workflow body must be
deterministic, and appending to a second SQLite file is a real side effect. Routing
it through a ``@satay.task`` means a crash-and-resume reuses an append that already
completed (satay's own replay guarantee) instead of writing it a second time — see
``cuttlefish.episodic.store``'s module docstring for the one narrower race this
doesn't close (a crash strictly between the write landing and satay recording this
task's own completion), the same residual gap ``side_effect=True``/``idempotent``
tasks exist to narrow, not eliminate, for any effect that isn't itself
transactionally tied to satay's own journal.
"""

from __future__ import annotations

from typing import Any

import satay

from cuttlefish import runtime
from cuttlefish.episodic.events import EventPayload, decode_payload, encode_payload


@satay.task(side_effect=True)
async def append_episodic_event(
    task_id: str, event_type: str, data: dict[str, Any]
) -> dict[str, Any]:
    payload = decode_payload(event_type, data)
    event = runtime.current().episodic_store.append(task_id, payload)
    return {"seq": event.seq, "ts": event.ts.isoformat()}


async def journal(task_id: str, payload: EventPayload) -> None:
    """Encode `payload` and append it via the durable task. Call from a workflow body."""
    event_type, data = encode_payload(payload)
    await append_episodic_event(task_id, event_type, data)
