# ADR-0001: The core loop is a satay workflow, from the first commit

- Status: Accepted
- Date: 2026-08-23
- Deciders: Jian

## Context

sibei-flow already made this mistake once. Its agent loop is a plain `for` loop
accumulating messages and a transcript in local variables. Crash at turn 4 of 6 and
all of it is gone: the lease expires, the job is re-claimed, and the whole thing
restarts from the top, paying for every model call again. Durability was never
designed in, so it has to be retrofitted, and the retrofit is exactly the kind of
work nobody schedules until an incident forces it.

cuttlefish exists specifically to run unattended, for long stretches, holding
credentials, with nobody watching to notice a crash or restart it by hand. That is
a harder version of the same problem sibei-flow already has, not a milder one. If
the core loop is written as ordinary Python control flow first and made durable
later, the "later" is a rewrite of the part of the system that most needs to be
correct.

satay-runtime already solves this. It gives five durable primitives (task, sleep,
wait-for-event, map/gather, child workflow), replay from an append-only journal
that reuses recorded results, and at-least-once execution with idempotency keys
derived from the run itself. It is a real, released dependency (0.1.0 on PyPI,
Apache-2.0, one process, local SQLite, no infrastructure to stand up) and this
project would be its first real external consumer. Nobody else in this family has
actually depended on it as a library yet; sibei-flow was meant to but the port was
deferred, so this repo carries some of the risk of being the one that finds the
rough edges in satay's own public surface.

## Decision

**cuttlefish's task loop is a `@satay.workflow` from the first line of code that
runs a task, not a plain async function that gets wrapped later.** Every LLM call
and every delegation to kopicode is a `@satay.task`. The CLI's `run` command opens
a satay app (`async with satay.run_app() as store:`), starts the workflow, and
waits on its result.

Two consequences follow directly and are treated as requirements, not nice-to-haves:

- **A killed process must resume cleanly.** Turns already completed replay from the
  journal instead of re-running, and the interrupted call resumes rather than
  restarting the whole task. This is one of slice 1's checkable acceptance
  criteria, not an aspiration for later.
- **The LLM provider call itself is a task, not a bare function call in the
  workflow body.** satay's nondeterminism detection is strict by default, and a
  workflow whose branching depends on something it didn't durably record (a raw
  network call, the clock, an environment variable) will fail replay the first
  time it actually needs to. Writing the provider call as a task from the start
  costs nothing now and avoids a rewrite later.

## Alternatives considered

| Option | Why not |
|--------|---------|
| A plain async loop, add durability once there's a reason to. | This is sibei-flow's actual history, and the ADR that would follow it already exists in that repo: the retrofit needed a dedicated PR and had to land before launch. Nothing about cuttlefish's use case is less demanding than sibei-flow's. |
| A different durable-execution runtime (Temporal, Restate, DBOS, Inngest, Hatchet). | All are real, but every one of them is either hosted infrastructure this project doesn't need, or a competing local runtime with no relationship to the rest of this suite. satay-runtime is local, in-process, and already the sibling project built for exactly this job; picking a different one buys nothing and costs the shared debugging story (Satay Studio's fork-and-compare). |
| Roll a bespoke append-only log, the way kopicode does. | kopicode made that choice deliberately, for a different reason: it needed a journal but explicitly rejected durable execution (ADR-0002 in that repo) because a coding agent's state that matters is the filesystem, and git already versions filesystems. cuttlefish's state is the task itself, not a working tree, so the argument that ruled satay out for kopicode doesn't apply here. |

## Consequences

This buys crash recovery for free, from the first working slice, and a debugger
(Satay Studio) that can fork a run from any prior turn and compare two runs
call by call - genuinely useful once a delegation to kopicode goes wrong in a way
that isn't obvious from the final result alone.

It costs real constraints. satay is one process, one writer: cuttlefish cannot run
two tasks concurrently until satay itself supports multi-worker execution, which it
doesn't yet. Every provider call and every delegation has to be written as a
durable primitive, which is more ceremony than a bare `await`, and getting the
task/workflow boundary wrong is the kind of mistake that only shows up on replay,
not on a first successful run. And because this project is satay's first real
external tenant, some of what breaks will be gaps in satay's own public surface
rather than bugs in this repo - that risk is accepted, not hidden, and is one of
this plan's open risks.
