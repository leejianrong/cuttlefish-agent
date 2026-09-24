# ADR-0010: Session continuity is a resume layer cuttlefish must build on top of satay's already-durable primitive — extend, don't replace

- Status: Accepted
- Date: 2026-09-25
- Deciders: Jian

## Context

KAN-1702 (CUT-E8, top priority): audit satay-runtime's continuity/replay model
against real failure modes — crash mid-delegation-round, the fleet daemon's own
restart, `cuttlefish.handover.maybe_handover`'s chained-summary fidelity across
many rounds, multi-project concurrent load — against Paperclip's DB-backed
"heartbeat" model, where an agent resumes persistent state rather than
restarting from a fresh stateless CLI call per round
(`project_paperclip_positioning`). **Jian's explicit instruction: get this to
Paperclip-par reliability or better, and revamp or replace satay-runtime
entirely if that's what it takes — nothing about keeping satay is assumed
going in.** This ADR is that decision, reasoned from satay-runtime's own
source (`/home/jianlee/projects/abang-ai/satay-runtime`) and cuttlefish's own,
not from either project's docs alone.

Four failure modes, checked directly, not assumed:

### 1. Crash mid-delegation-round: satay's own resume primitive is real, mature, and tested — and cuttlefish never calls it

`satay.api.runner.RunController.result()` (`satay/src/satay/api/runner.py:97-131`)
is exactly the mechanism a crash-recovery story needs: given a `run_id` whose
store row is non-terminal, it appends `WorkflowResumed` and re-drives the
`ReplayEngine` from the journal, reusing every already-completed task's result
rather than re-running it. `tests/integration/test_crash_recovery.py` proves
this works, including at task-argument granularity: kill the process right
after `delegate_to_agent_backend`'s `TaskCompleted` commits, call
`satay.start(run_task, task_input, run_id=task_id, store=store)` again, and
kopicode is invoked exactly once — the counting wrapper proves it, not just an
assertion on the returned status. This is real durability, not aspirational
durability, and at-least-once task execution with a per-invocation idempotency
key (ADR-0006 in satay-runtime, `ctx.idempotency_key` embeds `run_id`) is an
honest, load-bearing guarantee, not a marketing claim.

**But nothing in cuttlefish's own surface ever exercises this path outside a
test.** `cuttlefish.cli` mints `task_id = str(uuid.uuid4())` (a fresh id) on
every `cuttlefish run` invocation and `team_id = str(uuid.uuid4())` on every
`cuttlefish run-team` — grep confirms there is no `--resume <id>` flag and no
code path anywhere in `src/cuttlefish/` that calls `satay.start(..., run_id=)`
with an id from a *previous* invocation. `cuttlefish.fleet.daemon.FleetDaemon
.start` does the identical thing: `team_id = uuid.uuid4().hex`, always fresh.
So when a real `cuttlefish run` process is killed (OOM, a laptop sleeping, a
SIGKILL), the interrupted run's row sits in `.satay/` forever, genuinely
resumable by satay's own primitive — but nothing will ever call it that way,
because the only thing anyone can do next is start a *new* run with a *new*
id, which shares no journal with the crashed one. The gap Jian asked this
audit to find isn't in satay's replay engine. It's that cuttlefish never wires
a real operator, or the daemon, into the resume path satay's own test suite
already proves works.

A second, real risk this same audit surfaced: `delegate_to_agent_backend` is
`@satay.task(side_effect=True)` with no `idempotent=True` and no retries
(ADR-0006's own default). A crash *during* a live kopicode/Claude Code
invocation — before its `TaskCompleted` commits, not after — means resuming
that run re-executes the delegation from scratch: a second real invocation
against the same, possibly partially-edited, git working tree. This is
exactly the "at-least-once, ambiguous completion" case satay-runtime's ADR-0006
names and accepts as a general policy, not a bug — but cuttlefish has never
had to reckon with it concretely because nobody has ever actually resumed a
production run. Wiring up resume (this ADR's decision) makes this a real,
now-reachable risk that has to be designed for, not an inert theoretical one.

### 2. Daemon restart

Already named honestly in ADR-0009's own Consequences: `cuttlefish serve`
drives every project's team as an in-process `asyncio.Task`; killing the
daemon process ends every team it owns, and there is no separate supervisor.
What this audit adds: `cuttlefish.projects.store.Project.last_team_id`
(`src/cuttlefish/projects/store.py:88`) is *already* persisted to
`~/.cuttlefish/projects.db` on every `FleetDaemon.start` call
(`record_team_started`, `daemon.py:173`) — the exact id a restarted daemon
would need to resume that project's last team via finding #1's same
mechanism, if `FleetDaemon.start` is ever taught to pass it as `run_id`
instead of always minting `uuid.uuid4().hex`. The daemon restart gap and the
crash-mid-round gap are the same underlying gap (cuttlefish never resumes by
run_id), not two independent problems.

### 3. Handover-summary fidelity across many chained rounds

This turned out to be closer to a non-question than the audit assumed going
in: `maybe_handover` (`src/cuttlefish/handover.py:78`) checkpoints a
summarised window to the episodic journal as a `HandoverWritten` event once a
token budget is crossed — but grep across `src/cuttlefish/` (excluding
`handover.py` itself) shows **no caller ever reads `HandoverWritten` back**
into a subsequent round's prompt, task text, or delegation call. It is a
write-only checkpoint: real, journaled, correctly role-scoped (ADR-0007), and
genuinely useful for a human reading `cuttlefish show` afterward — but it
supplies zero continuity to the agent itself. So "does the chained-summary
approach hold fidelity across many rounds" doesn't quite apply: the mechanism
that's supposed to carry chained context *isn't in the loop at all*.

What actually threads round-to-round context today is a completely separate,
simpler mechanism: `cuttlefish.steering.compose_steered_text`
(`steering.py:47`) folds a growing `round_summaries: list[str]` — the raw
`DelegationCompleted.summary` / `DelegationRefused/Failed.reason` text of
*every* prior round — verbatim into each new round's task text, with **no
token budget, no compaction, no cap of any kind**. `maybe_handover`'s own
token-budget discipline (ADR-0004's whole reason for existing) governs the
journal-side checkpoint but never touches this list. A steerable task or team
role that runs many rounds (exactly the long-running, many-round case Jian
asked this audit to stress) grows its per-round prompt linearly and
unboundedly, forever, with zero drift protection — the opposite of what
ADR-0004's working-memory tier was built to prevent, and the opposite of
Paperclip's bounded, incrementally-resumed session state. This is a real,
concrete correctness gap this audit found, not a hypothetical one, and it sits
entirely on cuttlefish's own side — satay is not involved in this failure mode
at all (`round_summaries` is workflow-local state, correctly and
deterministically reconstructed on replay from journaled `Delegation*`
events; satay's replay never loses or corrupts it).

### 4. Multi-project concurrent load

No new finding here beyond what ADR-0009 already established and verified
against source: `satay.control.run_app(data_dir=...)` per project, each its
own `DataDirLock` (ADR-0017's H4 refinement, an exclusive OS advisory lock
refusing a second writer on the same data dir) and its own single-writer WAL
SQLite store (ADR-0012), coexisting as independent `asyncio` tasks under one
`contextvars.ContextVar`-scoped `Runtime` per project. This holds up under the
architecture as designed. It has not been stress-tested live at anything past
a 2-role, 1-2-project scale (`project_d1d2_live_usage_findings`); that's a
verification task (KAN-1704's stress-test scope), not a design gap this ADR
needs to resolve.

## Decision

**satay-runtime is not replaced.** Its actual continuity primitive — resume a
non-terminal run by calling `satay.start` again with the same `run_id`,
proven end-to-end by `test_crash_recovery.py` against the real, complete
`run_task` workflow — is sound, already at Paperclip-par *as a mechanism*.
Nothing this audit found is a defect in satay's replay engine, its
single-writer model, or its persistence layout; every real gap found is
cuttlefish never calling the primitive that already exists. Revamping or
replacing satay-runtime, per Jian's own standing instruction to consider it
seriously rather than assume it away, would mean re-deriving at-least-once
task execution, idempotency-key derivation, WAL-mode single-writer discipline,
and a working replay engine from scratch, to arrive at the same place a
one-line change (pass the *right* `run_id`) already reaches. That is not
"extend vs. replace" as a close call — it is not a close call.

**Continuity becomes a cuttlefish-owned resume layer, sitting entirely above
satay's existing surface, with three concrete pieces:**

1. **A reachable resume path, CLI and daemon.** `cuttlefish run`/`run-team`
   gain a `--resume <task-id>` flag that calls `satay.start` with that id
   instead of minting a fresh `uuid.uuid4()` — reaching exactly the path
   `test_crash_recovery.py` already proves correct, from a real second
   invocation rather than only a test harness. `FleetDaemon.start` gains the
   daemon-side half: on `cuttlefish serve` startup, scan `ProjectStore` for
   every project whose `last_team_id` is set and non-terminal (a plain read
   against that project's own `.cuttlefish/episodic.db`, the same read
   `FleetDaemon.status` already does), and resume each one by passing that
   `last_team_id` as `run_id` instead of a fresh one — closing the daemon-
   restart gap (finding #2) with the identical mechanism as the CLI gap
   (finding #1), not a second bespoke one. This is KAN-1703's concrete scope,
   sharpened by this audit from "daemon restart loses running-team state" to
   "wire the daemon's own startup into the resume primitive it already has
   the run_id for."

2. **A named, accepted risk for a crash strictly inside a live delegation.**
   Resuming a run crashed mid-invocation re-executes `delegate_to_agent_backend`
   against a possibly-already-edited working tree (finding #1's second half).
   This ADR does not solve it — cuttlefish's own "wraps the backend's existing
   headless surface as it exists, no new protocol" discipline (ADR-0003/0005)
   rules out inventing an idempotency handshake kopicode/Claude Code don't
   offer. It is named here, honestly, as a real and now-reachable consequence
   of shipping resume (item 1), the same posture ADR-0006 in satay-runtime
   itself already takes toward at-least-once execution generally — an
   operator resuming a crashed-mid-round task should be told, in the CLI's own
   output, that the in-flight round may re-run against a dirty working tree,
   not left to discover it.

3. **Handover summaries actually feed the loop they're named for.**
   `compose_steered_text` changes to fold in the *latest* `HandoverWritten`
   summary for the task/role (a bounded, single LLM-compressed string) in
   place of the raw, unbounded `round_summaries` list once one exists —
   `maybe_handover`'s own token-budget check becomes the compaction step this
   mechanism has needed since ADR-0004 but never had wired to it. This makes
   "does the chained summary hold fidelity across many rounds" a real,
   testable question for the first time, and fixes the concrete unbounded-
   growth defect finding #3 names. This is KAN-1704's sharpened scope: not
   only a stress test of an existing mechanism, but fixing the wiring gap the
   stress test would otherwise just rediscover.

**Multi-project concurrency (finding #4) needs no design change** — it stays
exactly as ADR-0009 shipped it. KAN-1704 verifies it live at real scale
instead.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Replace satay-runtime with a cuttlefish-owned, DB-backed "heartbeat" continuity layer, matching Paperclip's own architecture directly. | Paperclip's model works for them because their agent *sessions* are themselves the resumable unit — a different backend-integration shape than cuttlefish's own ADR-0003/0005 "wrap the tool's existing one-shot headless surface, invent no new protocol" boundary allows. Copying Paperclip's mechanism would mean either violating that boundary (giving kopicode/Claude Code a live, resumable session neither tool's headless CLI offers) or building an entirely parallel durability system that duplicates what satay's replay engine, proven by a real test against the real workflow, already does correctly. Named seriously per Jian's instruction, not dismissed by default — and rejected on the evidence, not the assumption. |
| Leave satay's resume primitive alone and build cuttlefish's own crash-detection/restart wrapper around whole `cuttlefish run` processes (e.g., a shell-level retry loop). | Solves "the process restarts" but not "the restarted process resumes the *same* run" — without passing the original `run_id` back in, a naive restart just starts a second, unrelated run, journaling a duplicate `TaskSubmitted` against a fresh id and abandoning the first run's row exactly as today. The actual fix has to be at the `run_id` layer this ADR targets, not the process-supervision layer (that's KAN-1703/1709's separate, real, and still-needed concern for the daemon process itself). |
| Treat findings #1-#3 as already covered by ADR-0009's Consequences section and close KAN-1702 without a new ADR. | ADR-0009 named the daemon-restart symptom but not its root cause (cuttlefish never resumes by run_id at all, which also explains the CLI-level crash gap ADR-0009 never covered) or the handover-summary wiring gap, which is new here. Jian's instruction was explicit: a real ADR recording the extend/layer/replace decision, not a pointer to an existing one that didn't ask this question. |

## Consequences

Continuity remains architecturally different from Paperclip's — stateless,
one-shot backend invocations wrapped by a durable orchestrator, rather than
persistent, resumable agent sessions — and this ADR keeps that difference
rather than converging on Paperclip's shape. Reaching Paperclip-par
reliability *within* that architecture means the three pieces above actually
ship, not that the architecture itself needs to change; this ADR is a decision
to finish wiring cuttlefish into a primitive it already depends on, not a
decision to build a new one.

KAN-1703's scope is sharpened by this audit (daemon-startup resume via the
already-persisted `last_team_id`, not undesigned process supervision from
scratch) and KAN-1704's scope grows by one concrete fix (handover summaries
actually feeding `compose_steered_text`) beyond its original "stress-test"
framing. `cuttlefish.handover`'s own module docstring will need a line
correcting "nothing is dropped from the record, only from live context" to
say what currently *reads back* from that record once item 3 ships — it
currently implies a round-trip that doesn't exist yet.

The crash-mid-delegation risk named in item 2 is a real, user-facing edge case
that resume (item 1) makes reachable for the first time; it is accepted and
surfaced honestly (a CLI warning), not solved, the same posture satay-runtime's
own ADR-0006 already takes toward at-least-once execution in general — not a
new inconsistency this ADR introduces, but an existing one this ADR is the
first place cuttlefish has had to actually confront.
