# ADR-0007: A team is concurrent roles sharing one task id; steering waits on satay's own control API

- Status: Accepted
- Date: 2026-09-20
- Deciders: Jian

## Context

Slice C (docs/SLICES.md) is named "multi-agent handover and steerable chat" —
generalizing V1's per-task working-memory handover (ADR-0004) across a team of
roughly three coding sub-agents per project, plus letting a human redirect a
still-running agent's work rather than only read its history afterward (Q32).
Neither half had a concrete design yet; PLAN.md's own Open risks explicitly deferred
both ("the full design" for roles, "the workflow-shape work" for steering).

Two research findings from implementing this slice reshaped both halves before any
code was written:

**Steering needs more than the primitive.** `satay.wait_for_event`/`satay.send_event`
already do exactly what a steering message needs (Q32's own finding). What was
missing was a way for anything *outside* the `cuttlefish run` process to reach it
while it runs — `cuttlefish run` is one blocking CLI invocation with nothing
listening, and satay's own control/read HTTP API (the thing that *can* be reached
externally) only ever ran as part of `satay dev`'s whole interactive-session model,
a different grain entirely. Building this properly meant asking satay-runtime for a
new, narrowly-scoped capability rather than working around the gap inside
cuttlefish — consistent with the standing instruction that satay's own roadmap now
follows cuttlefish-crew's needs (docs/QUESTIONS.md Q33). satay-runtime PR #101
(ADR-0046 there) added `satay.control.run_app`: `run_app`'s exact ergonomics, with
the control/read API composed in for the life of one `async with` block. This
shipped as satay `0.2.0`.

**A "team" needs an identity answer before it needs a persona design.** ADR-0001
(Q6) is explicit: a task's id is the satay run id it was started with, no second
identity scheme. `satay.start_child` mints a *new*, only-known-after-the-fact run id
for each child workflow — there is no way for a parent to pre-compute a child's own
run id and hand it to that child as its own `task_id` before starting it, so reusing
`run_task` verbatim as one child per role would either need a second identity
scheme (rejected on sight) or a deeper refactor of how every task-journaling call
learns its own id (out of proportion to this slice). The concurrency this slice
actually needs — several delegations genuinely running at once — doesn't need
separate satay runs at all: `delegate_to_agent_backend` is already a `@satay.task`,
and `satay.gather` already runs several durable calls concurrently within one
workflow. What's actually missing is a `role` tag on the shared journal's events and
a role-aware filter in the handover algorithm — additive, not a new identity scheme.

## Decision

**A team is one satay run — one `task_id` — running N roles' delegations
concurrently via `satay.gather`, not N child workflows.** `cuttlefish.team.run_team`
takes a list of `RoleInput` (`name`, `text`, optionally its own `allow`/
`secret_names`) under one `team_id`/`root`/`project`, journals each role's
`TaskSubmitted`/`DelegationStarted` up front, then gathers every role's
`delegate_to_agent_backend` call with `return_exceptions=True` (ADR-0027's collect
mode) so one role's failure doesn't take down the roles that already succeeded, then
journals each role's own outcome and runs that role's own handover check.

**Every event `run_team` writes carries a `role: str | None` field** — new on
`TaskSubmitted`, `DelegationStarted`, `DelegationCompleted`, `DelegationRefused`,
`DelegationFailed`, `HandoverWritten`, `TaskCompleted`, `TaskFailed`, all defaulting
to `None` (ADR-0004's forward-compatible unmarshalling: an event written by V1
through slice B, which never set this field, decodes to `None` unchanged — the
single-task case it always was). `cuttlefish show <task_id>` renders every role's
activity interleaved under the one id operators already know how to ask for, not N
ids they'd have to track themselves.

**`maybe_handover` gains an optional `role` filter.** Its algorithm is unchanged —
find the window since the last matching `HandoverWritten`, summarise once it crosses
budget — it now only ever looks at events whose own `role` equals the one asked for
(including `None`, which is exactly today's single-task behaviour, unchanged byte
for byte). Each role's own context bloat is caught and distilled independently;
one chatty role's journal cannot force another's window closed early, and cannot
suppress another's own next handover by writing a `HandoverWritten` that isn't
tagged for it.

**A role's own personality/functional-role content is out of scope for this ADR.**
`RoleInput.text` is exactly what the operator declares (`cuttlefish run-team --role
builder:"..."`), the same "operator declares it, cuttlefish doesn't infer it"
discipline `--allow`/`--secret` already established. Whether "builder"/"reviewer"/
"ops-checker" get real distinct system-prompt personas, and whether roles ever
coordinate with each other (a reviewer reacting to a builder's diff), is real,
open product design (Q31's "full design" is still deferred) — this ADR builds the
mechanism three independent, concurrently-running roles need, not the roles
themselves.

**Steering is now unblocked but not yet wired into cuttlefish.** satay `0.2.0`
(satay-runtime PR #101) ships `satay.control.run_app`; cuttlefish's own
`--secret`/`--allow` and delegation code needs its own follow-up slice to actually
adopt it (`cuttlefish run --steerable`, a `cuttlefish steer <task-id> "<message>"`
CLI command, a `SteeringMessage` event type, and the workflow-shape work — racing a
short `wait_for_event` against normal delegation progress — PLAN.md's own Open
risks already named as cuttlefish's job, not satay's). Named here as the deliberate
boundary of this ADR: the team-concurrency half ships now; the steering half is
next, once cuttlefish's own dependency on `satay>=0.2.0` is in place and verified
live.

## Alternatives considered

| Option | Why not |
|--------|---------|
| One child workflow (`start_child`) per role, its own journal. | Needs a child to know its own satay run id *before* it can journal its first event under that id as `task_id` — no such hook exists without a deeper refactor of how journaling learns its own id, and inventing a second identity scheme for teams specifically is exactly what ADR-0001/Q6 already rejected. |
| Have `cuttlefish` infer/decompose one operator task into N role-specific tasks via its own LLM planning step. | A real, separate product decision (an LLM-driven planning/decomposition step cuttlefish doesn't have today) — conflated with the concurrency mechanism this ADR is actually about. The operator already declares `--allow`/`--secret` explicitly; declaring each role's own task text explicitly is the same discipline, not a regression. |
| Wait for a real cross-tenant need before asking satay-runtime for anything. | Steering was already decided as buildable and wanted (Q32); the gap discovered while implementing it was concrete and immediate, not speculative — this is the standing instruction (Q33) applied, not a departure from the discipline that guards against building ahead of a proven need elsewhere in this project. |
| Fold steering into this same ADR/PR. | The two halves have genuinely independent dependencies: team concurrency needs nothing new from satay 0.1.0; steering needs satay 0.2.0 to actually exist and be installable. Shipping the half that's ready now, rather than blocking it on the half that isn't, is the same incremental discipline every prior slice already followed. |

## Consequences

An operator can run three genuinely concurrent delegations against one project
today, each independently handed-over, with no new satay capability and no change
to how a task's identity works. `cuttlefish show` keeps working unchanged for every
event written before this slice, and for a plain `cuttlefish run` after it (`role`
is always `None` there).

**Verified live, 2026-09-20: `satay.gather` genuinely overlaps the roles in wall
time** — a two-role team pointed at a fake, sleeping backend binary completed in
one sleep's duration, not two, confirming this is real concurrency and not a
`return_exceptions=True` fan-out that still executes members one at a time.

**Also verified live the same day, against the real kopicode binary, a real gap
this ADR names rather than solves**: kopicode itself takes an exclusive
per-working-tree session lock (`.kopicode/lock`), so two roles sharing one `--root`
both really do start concurrently, but the second's kopicode process immediately
refuses ("another kopicode session is already running in this working tree") once
the first already holds it. This is not a bug in the concurrency mechanism above —
it is kopicode's own guard against exactly the hazard two agents editing one
uncommitted working tree at once would otherwise risk (a corrupted git index, one
role's uncommitted edit stepping on another's), and cuttlefish has no standing to
route around a safety property a backend deliberately enforces. Two roles that
genuinely need to edit concurrently need separate working trees (their own
checkouts), not a shared `--root` — real, deferred work (docs/QUESTIONS.md's next
entry), not attempted here. Whether headless Claude Code enforces the same kind of
lock is unverified (no live run attempted, to avoid an unnecessary real cost/API
call) — named honestly as unknown rather than assumed either way, the same
discipline ADR-0005's Q36/Q37 already hold to for this backend.

It costs a real, if bounded, widening of the episodic schema — eight event types
each gained a field — and a filtering condition every future new event-consuming
code path (handover, any future summarisation, a dashboard's own read path) now has
to remember exists. `delegate_to_agent_backend`'s `return_exceptions=True` path
means a team's own result-processing loop has to unwrap `satay.TaskFailedError`
itself (`.error_type`/`.error_message`) to journal a faithful `DelegationFailed`
reason, a small extra case `run_task`'s own single-delegation path never needed
since it awaits its one call directly rather than collecting it.

The steering half remains real, named, unbuilt work — not deferred speculatively,
but blocked on a concrete, already-satisfied precondition (satay 0.2.0 existing and
installable) rather than an open design question.
