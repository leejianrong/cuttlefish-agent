# ADR-0009: A `Project` is a registry entry outside any single `.cuttlefish/`; the fleet daemon runs every project's team concurrently in one process, no subprocess per project

- Status: Accepted
- Date: 2026-09-22
- Deciders: Jian

## Context

Slice C left the roadmap at "next up is slice D, the dashboard/office UI" (`docs/PLAN.md`).
`docs/SLICES.md` only stubs it: "a game-like pixel-art virtual office per project, plus a
zoomed-out portfolio view across many projects." Two things named but not designed:
`docs/QUESTIONS.md` Q31 (functional roles + personality, "full design deferred to the
dashboard slice") and Q38 (`--project NAME` is a plain string, "a first-class `Project`
with its own identity is slice D's job"). Nothing about *how* a dashboard actually learns
what a sub-agent is doing, or how an operator gets from "click a project" to "a team is
running," existed before this ADR.

Jian scoped this before any code was written (three decisions, recorded here rather than
re-litigated): the dashboard is TypeScript + Svelte + Vite, not React — a build-tooling
choice this repo has never made before (it's been Python-only through V1-C). The dashboard
is a **fleet manager from day one**: it launches and owns each project's team, not just a
read-only view over teams an operator separately started in a terminal — this is the thing
that actually closes Q9's long-deferred "no daemon mode" gap. And the slice splits: **D1**
(this ADR) is the `Project` entity, the daemon, and a plain (non-game) UI wired to real
data; **D2** is the pixel-art skin on top of an already-proven API, not attempted here.

Two research findings, both checked directly against satay's source before designing
around them (the same discipline ADR-0008 already established for this project — verify a
composition before building on it, don't assume):

**A daemon that owns N projects' teams does not need N subprocesses, or satay-runtime's own
multi-worker milestone.** `satay.control.run_app` takes a `data_dir` parameter — nothing
in it assumes `Path.cwd()`. And `satay.timers`'s own poll-loop registry
(`_RUNNING_LOOPS: dict[int, tuple[Any, int]]`, keyed by `id(store)`) exists specifically to
guard against **the same store** getting two poll loops (ADR-0030), not to serialize
different stores — reading `register_poll_loop`/`unregister_poll_loop` directly confirms
this. Multiple `satay.control.run_app(data_dir=...)` blocks, each pointed at a different
project's own directory, each opening its own `DataDirLock` (a different lock per
directory, ADR-0017/Q54) and its own ephemeral-port HTTP server, coexist safely as
concurrent `asyncio` tasks inside one Python process. `docs/QUESTIONS.md` Q33/Q42's "no two
projects' cuttlefish tasks run concurrently yet ... satay-runtime's own multi-worker
milestone" is closed by this finding, not by that milestone: OS-level process concurrency
was never the only way to get there, and satay-runtime#100 (Postgres/multi-worker) remains
exactly as unneeded as Q33/Q42 already found for one project's own team.

**`cuttlefish.runtime` is the one real blocker, and it's a small, scoped fix.**
`cuttlefish/runtime.py` configures a plain module `global _runtime: Runtime | None`, "call
once, before starting any workflow" — true for a `cuttlefish run` process that only ever
drives one task, false the instant a daemon drives N projects' teams concurrently, each
needing its *own* `episodic_store`/`agent_backend`/`sandbox_provider`/`secrets_store`. Left
as a plain global, a second project's `runtime.configure()` call would silently repoint
every in-flight task's `journal()` writes at the wrong project's episodic store. Fixed by
promoting `_runtime` to a `contextvars.ContextVar[Runtime | None]` (`configure` becomes
`.set(...)`, `current` becomes `.get(...)`). `contextvars.Context` is copied at
`asyncio.create_task()` time and inherited by every task nested inside it — verified
against `satay.control.run_app`'s own implementation, whose `worker_task =
asyncio.create_task(worker.run())` and the replay engine's own internal task scheduling all
happen from *inside* the coroutine that already called `runtime.configure()` first, so
every nested task correctly inherits that project's `Runtime`, and a sibling project's task
(a disjoint `asyncio.create_task` from the daemon's own top-level loop) gets its own,
independent copy. A single `cuttlefish run` process calling `configure()` once at startup,
exactly as it does today, is unaffected — `ContextVar.set`/`.get` at the top of one linear
flow behaves identically to a plain global.

## Decision

### The `Project` entity lives outside any single project's own `.cuttlefish/`

Every store this project has built so far (`secrets.db`, `episodic.db`, satay's own
`.satay/`) is deliberately colocated with the project being worked on, rooted at whatever
directory `cuttlefish` is invoked from (`Path.cwd()`) — a convention, not a registry. A
fleet daemon needs the opposite: one registry that spans *every* project directory it
oversees, independent of which directory the daemon process itself happens to run from.

`cuttlefish.projects.ProjectStore` — a new SQLite store at `~/.cuttlefish/projects.db`
(hardcoded, no new env var this slice; `CUTTLEFISH_SECRETS_KEY`-style configurability is
real future work if a concrete need shows up, not built ahead of one). Holds:

```
Project:
  id: str            # uuid4 hex, generated at registration — stable identity a
                      # display name or a moved checkout can't accidentally break
  name: str           # display name, defaults to root's own directory name
  root: str           # absolute path — identical meaning to today's `--root`
  secrets_scope: str  # identical meaning to today's `--project NAME` (Q38) —
                       # defaults to `name`, so a project registered against an
                       # existing checkout keeps reading the same SecretsStore
                       # scope it already had before a Project entity existed
  roles: list[RoleDefinition]   # persistent role *definitions*, not task text
```

```
RoleDefinition:
  name: str      # matches a `--role NAME:...` name (ADR-0007)
  persona: str    # a short voice/personality description (Q31)
```

Nothing about `root`'s own `.cuttlefish/` directory changes. The daemon spawns each
project's satay engine with `data_dir`/episodic-store paths under that project's own
`root`, exactly where running `cuttlefish run-team` by hand already puts them — a project
registered here today, then later run by hand without the dashboard at all, reads and
writes the identical files either way. `ProjectStore.register`/`list`/`get`/`update_roles`/
`deregister` — `deregister` only removes the registry row, never touches `root` or its
`.cuttlefish/` contents (the same non-destructive posture `cuttlefish secrets delete`
already holds for one name, extended to a whole project entry).

**Role definitions are personas, not tasks.** A registered role's `persona` is durable
(Q31's "distinct personalities/voice"); the *task text* a role runs is supplied fresh each
time a team starts (identical to today's `cuttlefish run-team --role NAME:TASK_TEXT`
shape) — task text is inherently per-run, and forcing it to be persistent on the `Project`
row would make "start the same project again with a different ask" impossible without
first mutating the registry. Starting a team composes each role's stored `persona` onto
that round's task text (`f"You are {name}. {persona}\n\n{task_text}"`), the same
prompt-composition discipline `cuttlefish.steering.compose_steered_text` already
established for a steered round — extended here to a team's *first* round, not only its
steered ones. A role name supplied at start time that isn't in the project's own
`roles` just runs with no persona prefix (a graceful default, not a rejected request) —
registering roles ahead of time is a convenience, not a requirement to run a team at all.

### The fleet daemon: one process, N concurrent in-process teams, no subprocess per project

`cuttlefish.fleet.FleetDaemon` — the process `cuttlefish serve` starts. Holds an open
`ProjectStore`, a FastAPI app (see below), and an in-memory `dict[project_id, RunningTeam]`.

**Starting a project's team** (`POST /api/projects/{id}/start`, body: `{"roles":
[{"name", "text"}, ...]}`):

```python
async def _run_project_team(project: Project, roles: list[RoleInput], team_id: str) -> None:
    runtime.configure(build_runtime_for(project))  # this task's own ContextVar value
    workflow_input = {"team_id": team_id, "root": project.root, "project": project.secrets_scope,
                       "roles": roles, "steerable": True}
    async with satay.control.run_app(data_dir=Path(project.root) / ".satay") as app:
        daemon.register_running(project.id, team_id, app.base_url, app.token)
        try:
            handle = satay.start(run_team, workflow_input, run_id=team_id, store=app.store)
            result = await handle.result()
            daemon.record_result(project.id, team_id, result)
        except satay.WorkflowFailedError as exc:
            daemon.record_result(project.id, team_id, {"status": "error", "error": str(exc)})
        finally:
            daemon.unregister_running(project.id)
```

launched as `asyncio.create_task(_run_project_team(...))` — not awaited by the HTTP
handler, which returns `202` immediately with `team_id`. `steerable: True` unconditionally:
every daemon-launched team is steerable, since the dashboard's whole point is a live chat
panel per role (ADR-0008's plumbing, reused exactly as built, zero changes to
`cuttlefish.team`/`cuttlefish.workflow`/`cuttlefish.steering` needed for this). A project's
own `ProjectStore` row gets its `last_team_id` updated at start, so a `GET
/api/projects/{id}/status` right after a daemon restart can still find and read that
team's episodic events even though the in-memory `RunningTeam` registry was lost with the
old process (a genuinely still-running subprocess-free team has no PID to rediscover after
a daemon restart either — see Consequences).

**Stopping** (`POST /api/projects/{id}/stop`): `POST {base_url}/runs/{team_id}/cancel`
against that project's own running `app.base_url`/`app.token` (satay's own, already-built
`ControlAPI.cancel`/`POST /runs/{id}/cancel` route — a graceful, already-proven primitive
this ADR didn't have to invent). Cancellation still can't interrupt a coding-agent
invocation genuinely mid-flight (ADR-0008's already-named, still-open gap, extended here
rather than re-litigated) — a cancel enqueued while a round is running takes effect at
that round's own natural end, identically to how a queued `SteeringMessage` already does.

**Steering** (`POST /api/projects/{id}/steer`, body `{"role", "text"}`): looks up the
project's `RunningTeam.base_url`/`.token`, calls `cuttlefish.steering.send_steering_message`
directly — the exact function `cuttlefish steer` already uses, imported and called
in-process rather than shelled out to, since the daemon already holds everything that
function needs.

**Status** (`GET /api/projects` / `GET /api/projects/{id}/status`): never asks satay for
live state (ADR-0009/0012's own "reads go direct to the journal, never live worker state"
discipline, satay's own words). Reads that project's `.cuttlefish/episodic.db` directly
(`EpisodicStore.open(Path(project.root) / ".cuttlefish" / "episodic.db")`, read-only use —
WAL mode, already the store's own default, means an external reader never blocks or is
blocked by the daemon's own in-flight writer task) for `project.last_team_id`, and reduces
each role's own most recent events to one of five states — a state machine derived
entirely from event types this project already journals, no new event type needed
(ADR-0004's "no parallel transcript," held to exactly as before):

| State | Derived from |
|-------|--------------|
| `queued` | `TaskSubmitted` written, no `DelegationStarted` yet for this role |
| `working` | latest role event is `DelegationStarted`, no round-terminal event after it |
| `blocked` | latest role event is `DelegationRefused`, no further round after it |
| `done` | latest role event is `TaskCompleted` |
| `failed` | latest role event is `TaskFailed`, or `DelegationFailed` with no further round after it |

**Crash/liveness.** A `RunningTeam` whose `asyncio.Task` finished (successfully, via
`WorkflowFailedError`, or an unexpected exception) transitions out of "running" and its
final `result` is what `GET /api/projects/{id}/status` reports from then on — read from
`daemon`'s own in-memory `record_result`, falling back to the episodic journal's own
`TaskCompleted`/`TaskFailed` event if the daemon itself restarted meanwhile. **No
auto-restart.** A team that crashes or is stopped stays stopped until an operator starts it
again — real supervision (backoff, auto-restart policy) is exactly the kind of feature this
project's own standing discipline (ADR-0002, "don't build ahead of a proven need") says to
defer until a real gap is felt, not invent speculatively alongside everything else this
slice already does for the first time.

### The daemon's own HTTP surface

FastAPI + uvicorn — **no new dependency**: `satay[studio]` already pulls both in for
`satay.control.run_app` (ADR-0046, `pyproject.toml`'s own comment on the `[studio]` extra),
and this project's `ClaudeCodeBackend`/`KopicodeBackend`'s "no new protocol" discipline
(ADR-0003/0005) extends naturally to "no new *dependency* where an existing one already
covers the need," the same reasoning `cuttlefish.steering` already used to justify plain
`urllib.request` over a new HTTP client library.

Loopback-only bind (`127.0.0.1`, refusing anything else — satay's own `ensure_loopback_bind`
reused directly rather than reimplemented), a generated bearer token printed once at
`cuttlefish serve` startup and required on every request (`x-cuttlefish-token`, the same
header-name convention satay's own `x-satay-token`/`TOKEN_HEADER` (ADR-0014) already
established) — this daemon is a strictly higher-value target than a single task's own
control API (it can steer *every* registered project at once), so it gets the identical
posture, not a weaker one, even though it's cuttlefish's own server and satay's own
`SecurityPolicy` class isn't reused directly (it's `satay.control`-internal, not part of
the public `satay.control.__all__` surface this project imports from).

Routes: `GET /api/projects`, `POST /api/projects` (register), `GET /api/projects/{id}`,
`PATCH /api/projects/{id}/roles`, `DELETE /api/projects/{id}` (deregister only),
`POST /api/projects/{id}/start`, `POST /api/projects/{id}/stop`,
`GET /api/projects/{id}/status`, `POST /api/projects/{id}/steer`.

`cuttlefish projects add/list/remove` (CLI) manage the registry without the daemon running
at all — the same "every affordance has a CLI surface first" posture this project has held
since V1's `cuttlefish run`/`show`, extended rather than abandoned now that a UI exists.

### The frontend: Svelte + TypeScript + Vite, plain UI this slice, no game rendering yet

A new top-level `frontend/` directory — this repo's first non-Python build pipeline.
`npm create vite@latest -- --template svelte-ts`, a thin `fetch`-based API client typed
against the routes above (hand-written types mirroring the Python dataclasses this slice
adds — no OpenAPI-codegen machinery introduced for five routes). Two views: a portfolio
grid (`GET /api/projects`, one card per project: name, each role's status as a plain
colored chip, start/stop buttons) and a project detail view (role cards, a plain textarea +
send button per role posting to `/steer`, a scrolling plain-text tail of that role's recent
episodic events) — functionally equivalent to D2's eventual office/sprite view, deliberately
not art. `make frontend-check` (`svelte-check` + `tsc --noEmit`) and `make frontend-build`
join `make ci`, gating merges exactly as the Python suite already does — a green `make ci`
means both stacks pass, not just one.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Spawn `cuttlefish run-team --steerable` as an OS subprocess per project, parse its first stdout line for `task_id`/`base_url`/`token`. | Works, but reinvents process supervision (liveness, stdout framing, working-directory/env forwarding) this project doesn't need to own: `satay.control.run_app(data_dir=...)` plus one `ContextVar` fix gives the identical capability — N independent satay engines running concurrently — as plain `asyncio` tasks in one process, with zero new IPC surface. |
| Keep `cuttlefish.runtime` a plain global; serialize the daemon's own project starts so only one team ever runs at a time. | Defeats "fleet manager" before it exists — a dashboard that can only usefully run one project's team at once isn't the thing Jian asked for, and the actual fix (a `ContextVar`) is small, scoped, and doesn't change behavior for the single-task CLI path at all. |
| Poll satay's own `ReadAPI`/HTTP `timeline` for status instead of reading `.cuttlefish/episodic.db` directly. | Two problems: satay's own reads are explicitly journal-derived already (no "live worker state" shortcut exists to skip either way), and cuttlefish's *own* episodic events (not satay's raw `TASK_SCHEDULED`/`TASK_COMPLETED` primitives) are what already carry `role`/`DelegationStarted`/`SteeringMessage` — the exact shape a status view needs. Reading satay's own timeline would mean re-deriving cuttlefish's own event semantics a second time from a lower-level stream that doesn't carry them. |
| A registered `Project`'s `roles` also store default task text, not just persona. | Makes "run the same project again with a different ask" require editing the registry first — task text is inherently ephemeral (identical to today's `--role NAME:TASK_TEXT`), persona is the durable part (Q31), and conflating them buys nothing. |
| React + Vite (JS or TS) instead of Svelte. | Jian's own explicit stack choice — Svelte's compiled-output-not-virtual-DOM model and smaller runtime were the stated reason, not re-litigated here. |

## Consequences

A daemon restart loses every in-memory `RunningTeam` handle — a team started before the
restart keeps running (it's still a live `asyncio.Task` inside the *old* process, which the
daemon operator would have had to kill to restart at all; restarting the daemon process
necessarily ends every team it was running, there being no separate supervisor process
underneath it this slice). `GET /api/projects/{id}/status` right after a restart still
renders that project's *last* known state correctly (`last_team_id` plus a fresh
`.cuttlefish/episodic.db` read finds the team's terminal event if it reached one, or its
last known event if it didn't) — but a team genuinely still mid-round when the daemon died
shows as stalled at whatever its last journaled event was, with no way to tell "still
actually running (impossible, the process is gone)" from "the daemon died mid-round" from
this state alone. Named honestly as a gap: real process supervision (the daemon itself
being supervised, so it restarts without losing running teams) is out of scope for this
slice, the same "don't build ahead of a proven need" posture already used to defer
auto-restart above.

This closes Q9's "no daemon mode" gap for the first time since it was assumed away in V1 —
`cuttlefish serve` is a genuine long-running process, not a blocking one-shot CLI
invocation. It also means this project's process model now has two shapes side by side:
the original blocking `cuttlefish run`/`run-team` (unchanged, still the way to run one task
without the daemon at all) and the daemon's own always-on `asyncio.create_task`-per-team
shape — both drive the identical `run_task`/`run_team` workflows, so a project run by hand
today and a project run through the dashboard tomorrow write indistinguishable episodic
journals.

`cuttlefish.runtime`'s global-to-`ContextVar` change is the first change to a module every
prior slice treated as fixed "process-wide configuration" — its own module docstring
needs updating alongside the code, not left describing a constraint the daemon no longer
holds to.

`docs/QUESTIONS.md` gets new entries for the `Project`-entity/persona design, the
subprocess-vs-in-process finding, and the `ContextVar` fix. `docs/PLAN.md`'s Open risks
entry naming Q33/Q42's "many projects, many teams, concurrently" as satay-runtime's own
future multi-worker milestone is corrected here, not carried forward unchanged: D1 answers
it today, in-process, without that milestone.
