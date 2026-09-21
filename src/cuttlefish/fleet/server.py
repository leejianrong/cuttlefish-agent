"""The fleet daemon's HTTP surface (ADR-0009).

FastAPI -- no new dependency: `satay[studio]` already pulls in FastAPI/uvicorn for
`satay.control.run_app` (ADR-0046), and `cuttlefish run --steerable` already made
that pin unconditional (Q46), not an opt-in extra of cuttlefish's own.

Loopback-only bind and a per-session bearer token (`x-cuttlefish-token`) -- the same
posture satay's own control API holds (ADR-0014), reused directly via
`satay.control.SecurityPolicy`/`generate_token`/`ensure_loopback_bind` rather than
reimplemented, since this daemon is a strictly higher-value target than a single
task's own control API: it can steer *every* registered project at once.
"""

from __future__ import annotations

import dataclasses
import socket
from collections.abc import Awaitable, Callable
from typing import Any

import satay.control
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from cuttlefish.episodic.store import EpisodicEvent
from cuttlefish.fleet.daemon import FleetDaemon, FleetError, RoleStart
from cuttlefish.projects.store import ProjectNotFoundError, RoleDefinition

#: Distinct from satay's own `x-satay-token` (ADR-0046) -- a fleet-daemon request
#: and a per-task steering request must never be confused for one another.
TOKEN_HEADER = "x-cuttlefish-token"

#: Arbitrary, unregistered with IANA -- an operator with a real conflict overrides
#: it with `--port`, the same escape hatch `satay dev`'s own default port has.
DEFAULT_FLEET_PORT = 8420


def _project_json(daemon: FleetDaemon, project_id: str) -> dict[str, Any]:
    project = daemon.projects.get(project_id)
    return {
        "id": project.id,
        "name": project.name,
        "root": project.root,
        "secrets_scope": project.secrets_scope,
        "roles": [{"name": r.name, "persona": r.persona} for r in project.roles],
        "last_team_id": project.last_team_id,
        "allow": [list(command) for command in project.allow],
        "running": daemon.is_running(project.id),
        "status": daemon.status(project.id),
    }


def _event_json(event: EpisodicEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "ts": event.ts.isoformat(),
        "event_type": type(event.payload).__name__,
        "payload": dataclasses.asdict(event.payload),
    }


def _roles_from_body(body: dict[str, Any]) -> tuple[RoleDefinition, ...]:
    return tuple(
        RoleDefinition(name=r["name"], persona=r.get("persona", "")) for r in body.get("roles", [])
    )


def _allow_from_body(body: dict[str, Any]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(command) for command in body.get("allow", []))


def create_app(daemon: FleetDaemon, *, security: satay.control.SecurityPolicy) -> FastAPI:
    app = FastAPI(title="cuttlefish-crew fleet daemon")

    @app.middleware("http")
    async def _check_security(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            security.check(
                token=request.headers.get(TOKEN_HEADER),
                host=request.headers.get("host"),
                origin=request.headers.get("origin"),
            )
        except satay.control.AuthError as exc:
            return JSONResponse(status_code=exc.status, content={"detail": exc.detail})
        return await call_next(request)

    # Registered *after* `_check_security` so it wraps *outside* it (Starlette
    # applies the most-recently-added middleware first) -- a browser's CORS
    # preflight `OPTIONS` never carries the token header at all, so it must be
    # answered by `CORSMiddleware` itself, before `_check_security` ever sees it,
    # or every cross-origin request would fail before the real one is even sent.
    # The dashboard frontend (`frontend/`) is a separate origin during development
    # (Vite's own dev server, a different port); CORS only lets a browser's JS
    # *read* the response -- `_check_security` above is still the actual auth
    # boundary. Loopback-only, matching this whole surface's own posture
    # (ADR-0014) -- never a wildcard origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(127\.0\.0\.1|\[::1\]|localhost)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/projects")
    async def list_projects() -> dict[str, Any]:
        return {"projects": [_project_json(daemon, p.id) for p in daemon.projects.list()]}

    @app.post("/api/projects", status_code=201)
    async def register_project(request: Request) -> dict[str, Any]:
        body = await request.json()
        name, root = body.get("name"), body.get("root")
        if not name or not root:
            raise HTTPException(400, "'name' and 'root' are required")
        project = daemon.projects.register(
            name=name,
            root=root,
            secrets_scope=body.get("secrets_scope"),
            roles=_roles_from_body(body),
            allow=_allow_from_body(body),
        )
        return _project_json(daemon, project.id)

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        try:
            return _project_json(daemon, project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/projects/{project_id}/events")
    async def get_events(project_id: str) -> dict[str, Any]:
        try:
            events = daemon.events(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"events": [_event_json(event) for event in events]}

    @app.patch("/api/projects/{project_id}/roles")
    async def update_roles(project_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            daemon.projects.update_roles(project_id, _roles_from_body(body))
            return _project_json(daemon, project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.patch("/api/projects/{project_id}/allow")
    async def update_allow(project_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        try:
            daemon.projects.update_allow(project_id, _allow_from_body(body))
            return _project_json(daemon, project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def deregister_project(project_id: str) -> None:
        if not daemon.projects.deregister(project_id):
            raise HTTPException(404, f"project {project_id!r} not found")

    @app.post("/api/projects/{project_id}/start")
    async def start_project(project_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        roles: list[RoleStart] = [
            {"name": r["name"], "text": r["text"]} for r in body.get("roles", [])
        ]
        if not roles:
            raise HTTPException(400, "'roles' must have at least one {name, text}")
        try:
            team_id = await daemon.start(project_id, roles)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FleetError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"team_id": team_id}

    @app.post("/api/projects/{project_id}/stop")
    async def stop_project(project_id: str) -> dict[str, Any]:
        try:
            await daemon.stop(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FleetError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "stopping"}

    @app.post("/api/projects/{project_id}/steer")
    async def steer_project(project_id: str, request: Request) -> dict[str, Any]:
        body = await request.json()
        role, text = body.get("role"), body.get("text")
        if not role or not text:
            raise HTTPException(400, "'role' and 'text' are required")
        try:
            await daemon.steer(project_id, role, text)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FleetError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"status": "sent"}

    return app


def find_free_port(host: str, preferred: int, *, attempts: int = 20) -> int:
    """The first free port at or after `preferred` on `host` -- a plain
    `socket.bind` probe, pure stdlib (dev-playbook guidance: don't depend on
    `lsof`/`nc` being installed just to avoid a port collision).

    `cuttlefish serve` is meant to be a one-command entry point; on a personal
    machine already running several projects side by side, a hardcoded default
    port that just fails when it's taken is exactly the friction that guidance
    warns against -- the fix is trying the next port automatically and printing
    which one it actually landed on, not asking the operator to remember
    `--port` every time. A probe-then-release check is inherently racy (another
    process could grab the port in between) -- uvicorn's own bind is still what
    actually decides; this only picks a good first guess.
    """
    for candidate in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise RuntimeError(f"no free port found in [{preferred}, {preferred + attempts}) on {host!r}")


async def run_daemon(
    daemon: FleetDaemon, *, host: str = "127.0.0.1", port: int = DEFAULT_FLEET_PORT
) -> None:
    """Serve `daemon`'s HTTP surface until cancelled (`cuttlefish serve`).

    Prints the generated token once, to stdout -- the only place it's ever shown,
    the same posture `cuttlefish run --steerable` already holds for its own token.
    """
    satay.control.ensure_loopback_bind(host)
    resolved_port = find_free_port(host, port)
    token = satay.control.generate_token()
    app = create_app(daemon, security=satay.control.SecurityPolicy(token=token))
    # flush=True: a long-running daemon's stdout is commonly redirected to a log
    # file rather than a TTY, where Python fully buffers by default -- an operator
    # piping this to a file must still be able to read the token immediately,
    # not only once enough further output accumulates to flush the buffer.
    print(f"cuttlefish serve: http://{host}:{resolved_port}  {TOKEN_HEADER}: {token}", flush=True)
    config = uvicorn.Config(app, host=host, port=resolved_port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
