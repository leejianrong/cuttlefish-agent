"""The kopicode delegation: shells out to ``kopicode run --print`` (ADR-0003).

Wraps kopicode's existing headless surface as-is — no new protocol. Parses its
newline-delimited JSON stream (``cmd/kopicode/print.go``'s documented schema) into a
single, typed :class:`DelegationOutcome`, so a caller never has to know kopicode's
own event vocabulary.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Iterable, Mapping
from typing import Any, Literal

#: kopicode run --print's per-line `kind` values this module reads. Every other kind
#: (provider_request, tool_call_parsed, ...) is part of the real record but doesn't
#: change the outcome this module decides.
_KIND_STREAM = "stream"
_KIND_PERMISSION_DECIDED = "permission_decided"
_KIND_EDIT_APPLIED = "edit_applied"
_KIND_SESSION_ENDED = "session_ended"

#: permission_decided's `decision` field (kopicode internal/permission.Verdict).
_DECISION_DENY = "deny"

#: session_ended's exit_code: 0 is the only success value (kopicode internal/engine/stop.go).
_EXIT_CODE_SUCCESS = 0


class DelegationError(Exception):
    """The delegation call couldn't be completed at all.

    Raised for a condition outside kopicode's own recorded outcome — the binary
    missing, a stream with no parseable session in it at all. A refusal, or a
    session that ended without succeeding, is not this — see
    :class:`DelegationOutcome`.
    """


@dataclasses.dataclass(frozen=True, slots=True)
class DelegationOutcome:
    """What one ``kopicode run --print`` invocation produced, boiled down to one verdict.

    ``kind`` is exactly one of:

    - ``"completed"`` — kopicode finished (exit 0): at least one edit landed, or it
      had nothing to do (a read-only/informational task).
    - ``"refused"`` — kopicode's own permission gate declined the action it needed
      (denyHeadless's unconditional refusal today, or a declared policy's deny once
      one is configured, docs/QUESTIONS.md Q16), and no edit landed as a result.
    - ``"failed"`` — kopicode ran and recorded a session, but did not finish cleanly,
      for a reason other than a permission denial.
    """

    kind: Literal["completed", "refused", "failed"]
    summary: str
    edited_paths: list[str] = dataclasses.field(default_factory=list)
    reason: str | None = None


def classify_stream(events: Iterable[Mapping[str, Any]]) -> DelegationOutcome:
    """Reduce an already-parsed sequence of `run --print` event lines to one outcome.

    Pure and synchronous — the subprocess and its NDJSON parsing live in
    :func:`run_kopicode`, which calls this once the stream is fully read. Kept
    separate so this decision logic is unit-testable against literal, representative
    event sequences without a real kopicode process, while parsing an *actual*
    stream stays integration-tested against the real binary (docs/SLICES.md V1 test
    plan) — this function doesn't invent kopicode's vocabulary, it only decides what
    a given sequence of it means.
    """
    edited_paths: list[str] = []
    deny_reasons: list[str] = []
    session_ended: Mapping[str, Any] | None = None

    for event in events:
        kind = event.get("kind")
        if kind == _KIND_EDIT_APPLIED:
            path = event.get("path")
            if isinstance(path, str) and path:
                edited_paths.append(path)
        elif kind == _KIND_PERMISSION_DECIDED:
            if event.get("decision") == _DECISION_DENY:
                reason = event.get("reason")
                deny_reasons.append(reason if isinstance(reason, str) else "denied")
        elif kind == _KIND_SESSION_ENDED:
            session_ended = event

    if session_ended is None:
        raise DelegationError("kopicode's stream ended with no session_ended event")

    exit_code = session_ended.get("exit_code")
    stop_reason = session_ended.get("reason", "unknown")

    if edited_paths:
        return DelegationOutcome(
            kind="completed",
            summary=f"kopicode edited {len(edited_paths)} file(s) ({stop_reason})",
            edited_paths=edited_paths,
        )
    if deny_reasons:
        return DelegationOutcome(
            kind="refused",
            summary="kopicode's permission gate declined every action it needed",
            reason="; ".join(deny_reasons),
        )
    if exit_code == _EXIT_CODE_SUCCESS:
        return DelegationOutcome(
            kind="completed",
            summary=f"kopicode finished with no edit needed ({stop_reason})",
        )
    return DelegationOutcome(
        kind="failed",
        summary=f"kopicode did not finish cleanly ({stop_reason})",
        reason=f"exit_code={exit_code} reason={stop_reason}",
    )


async def run_kopicode(
    *,
    binary: str,
    task_text: str,
    root: str,
    policy_file: str | None = None,
    timeout: float | None = None,
) -> DelegationOutcome:
    """Run ``binary run --print task_text`` in `root` and classify what it did.

    Raises :class:`DelegationError` for anything short of a recorded session: the
    binary missing, a non-JSON line, or a stream with no `session_ended`. Anything
    kopicode itself recorded, cleanly or not, is a :class:`DelegationOutcome`, never
    an exception — QUESTIONS.md Q16's "caught, journaled as a typed episodic event"
    happens one layer up, in the satay task that calls this
    (``cuttlefish.tasks.delegate``).
    """
    args = [binary, "run", "--print"]
    if policy_file is not None:
        args += ["--policy-file", policy_file]
    args.append(task_text)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise DelegationError(f"kopicode binary {binary!r} not found") from exc

    assert process.stdout is not None
    assert process.stderr is not None
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            asyncio.gather(process.stdout.read(), process.stderr.read()), timeout=timeout
        )
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise DelegationError(f"kopicode timed out after {timeout}s") from exc
    await process.wait()

    events = _parse_ndjson(stdout_bytes)
    if not events:
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise DelegationError(
            f"kopicode produced no session events (exit {process.returncode}); "
            f"stderr: {stderr_text or '<empty>'}"
        )
    return classify_stream(events)


def _parse_ndjson(stdout_bytes: bytes) -> list[Mapping[str, Any]]:
    """Every non-header event line of a `run --print` stream, parsed as JSON."""
    events: list[Mapping[str, Any]] = []
    for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DelegationError(f"kopicode emitted a non-JSON line: {line!r}") from exc
        if not isinstance(parsed, dict):
            raise DelegationError(f"kopicode emitted a non-object JSON line: {line!r}")
        if parsed.get("kind") == _KIND_STREAM:
            continue
        events.append(parsed)
    return events
