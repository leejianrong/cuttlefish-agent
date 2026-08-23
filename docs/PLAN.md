# cuttlefish-agent: Plan

Status: agreed - Milestone: MVP (slice 1)

## Problem

Long-running agent assistants (OpenClaw, Hermes, and their kind) run unattended for
long stretches, but the ones available today handle memory badly. A crash loses
whatever context wasn't checkpointed, a long session either runs out of context or
gets summarised by hand, and nothing distills what actually worked into something
reusable next time. The operator either babysits the agent to catch these failures,
which defeats the point of it running unattended, or accepts that it periodically
loses the thread.

Separately, this suite already has a coding specialist (kopicode) built and
measured, and a durable-execution runtime (satay-runtime) built and released, but
nothing that supervises either of them over an unattended, long-running task.

## Solution

An operator gives cuttlefish a task in plain language. Cuttlefish works on it, and
if the task is a coding task, hands it to kopicode rather than attempting the edit
itself. If the process crashes partway through, restarting it resumes exactly where
it left off rather than starting over. Everything that happened is recorded in one
place the operator can read afterward, not scattered across logs that don't agree
with each other.

## Users and actors

- **The operator** (primary). The person who runs cuttlefish, configures what it's
  allowed to delegate, and holds the credentials it uses. Their trust boundary is
  final: nothing a submitted task asks for reaches further than what the operator
  already configured.
- **External tools and other agents** (secondary). They can submit tasks through
  the same CLI surface a human would use. They are not a distinct trust tier in the
  MVP - see ADR-0002's trust model - and get exactly the access the operator's
  running configuration grants, no more.
- **kopicode** (a dependency, not a user). The specialist cuttlefish delegates
  coding subtasks to, over its own existing headless interface (ADR-0003).

## Scope

**In this milestone.**

- One trigger surface: a CLI (`cuttlefish run "<task>"`), blocking until the task
  reaches a terminal state.
- The core loop as a `@satay.workflow` from the first line, with every LLM call and
  every kopicode delegation as a `@satay.task` (ADR-0001).
- Episodic memory: a durable, tagged-union event log in its own SQLite store, with
  write-time secret redaction (ADR-0004).
- Working memory: context-budget tracking and an automatic handover derived fresh
  from the episodic record at a threshold, never a hand-maintained document
  (ADR-0004).
- One delegation path to kopicode, gated by a hardcoded, narrow allowlist rather
  than a general policy mechanism (ADR-0003).
- Crash recovery: killing the process mid-task and restarting resumes correctly,
  without re-running a delegation that already completed.

**Out.**

- Chat or webhook trigger surfaces. The CLI is the only way in; anything else is a
  second surface this milestone doesn't need to prove the mechanism works.
- Procedural memory (skill distillation) and semantic memory. Named in ADR-0004,
  built by nobody here.
- A general, declarative permission policy for the kopicode delegation. The MVP's
  allowlist is hardcoded on purpose - the general form generalises once there's a
  second real policy to compare it against, the same discipline kopicode's own
  ADR-0005 already uses for its harness configuration axes.
- Real sandbox containment around the delegation (ADR-0002). Slice 1 accepts the
  same risk kopicode's own ADR-0008 accepts, for the same reason: one operator,
  their own task, their own machine.
- Any second delegation target beyond kopicode, and any multi-agent orchestration
  beyond the one supervisor/one specialist relationship. This milestone proves one
  delegation, not a swarm.
- cuttlefish-crate, or any spun-out sandbox product (ADR-0002). It doesn't exist
  until there's a second real consumer or a concrete reason to differentiate.
- A clarifying-question loop back to the operator when a task is ambiguous
  (Q18). The CLI's operator is present in principle, but this is genuinely
  additional scope past what the MVP needs to prove.

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | Given one real task, run it to a terminal state unattended, and produce a readable record of what happened. | Core goal |
| R1 | Survive a killed process: resuming after a crash reaches the same terminal state without re-running a delegation that already completed. | Must-have |
| R2 | Delegate at least one real coding subtask to kopicode successfully, over kopicode's existing headless interface. | Must-have |
| R3 | Track context usage during a task and produce an automatic handover at a threshold, derived from the episodic record rather than hand-maintained. | Must-have |
| R4 | Never lose or silently truncate a tool result or a model reply; everything a person reads back is derived from the episodic log, not a parallel transcript. | Must-have |
| R5 | Redact known secret values from the episodic log at write time. | Must-have |
| R6 | Refuse a delegation request that isn't on the configured allowlist, the same fail-closed posture kopicode's own permission gate uses. | Must-have |
| R7 | A second task submitted while one is running queues rather than being rejected or silently dropped. | Nice-to-have |

## Shape

| Part | Mechanism | ADR |
|------|-----------|-----|
| S1 | `@satay.workflow` core loop; every provider call and every kopicode delegation is a `@satay.task` | ADR-0001 |
| S2 | Kopicode delegation: a `side_effect=True` satay task shelling out to `kopicode run --print`, parsing its NDJSON stream, gated by kopicode's forthcoming ADR-0011 policy (kopicode board KAN-987) | ADR-0003 |
| S3 | Episodic journal: tagged-union events in `.cuttlefish/episodic.db` (SQLite), never truncated, versioned from the first commit, redacted at write time | ADR-0004 |
| S4 | Working-memory handover: triggered at a token-budget threshold, one bounded LLM call over the recent episodic window, written back as an episodic event | ADR-0004 |
| S5 | `LlmProvider` seam for cuttlefish's own reasoning calls: a keyless `replay` provider for tests, a real provider (Claude or an OpenAI-compatible endpoint) for actual runs | - |
| S6 | Sandbox provider interface (create/exec/snapshot/destroy), defined but not implemented in this milestone | ADR-0002 |

## Affordances

**Non-UI.**

| Affordance | Kind | Wires to |
|------------|------|----------|
| `cuttlefish run "<task>"` | CLI command | Opens a satay app, starts the task workflow, blocks for a terminal state, prints a JSON result |
| `cuttlefish show <task-id>` | CLI command | Reads the episodic journal for one task and renders it for a person |
| Delegation task | Internal satay task | Shells out to `kopicode run --print`, parses its event stream |
| Episodic journal | Local store | Every workflow and task boundary appends a typed event |

There is no UI in this milestone. The CLI's JSON output and `show` command are the
whole surface a person or another tool has to reason over.

## Implementation decisions

The workflow, its tasks, and the episodic journal are three separate concerns and
stay that way: satay owns replay identity and crash recovery (ADR-0001), the
episodic store owns the human-readable record of what happened (ADR-0004), and
neither substitutes for the other. A task's ID is the satay run ID it gets on
start; there is no second identity scheme (Q6).

The delegation task's failure handling is plain: a failed or refused delegation is
caught, written as a typed episodic event, and returned to the operator as a real
failure. It is not silently retried, and a missing kopicode binary on PATH is
checked at startup rather than discovered mid-task (Q16, Q17).

Concurrency in this milestone is sequential, not by choice but by inheritance: 
satay-runtime is one process, one writer, with no multi-worker execution yet. A
second submission queues in-process (Q8, R7).

## Testing approach

The primary seam is the workflow's public entry point, driven with satay's own
testing primitives: a `ManualClock`, a seeded RNG where needed, and its
`FaultInjector` to kill the process after a chosen journal event and assert that
resuming reaches the same terminal state without a duplicated delegation. That is
the same seam satay itself is tested through, and it is the one seam that actually
answers "did this behave correctly," rather than which internal function ran.

The kopicode delegation is tested against kopicode's own headless surface directly
(no mock kopicode), because the contract that matters is what `run --print`
actually emits, not an assumption about it. Both paths are exercisable now that
kopicode board KAN-987 has landed: the refusal-handling path against an
unconfigured `run --print` (still `denyHeadless` by default, unchanged), and the
"successfully edits a file" path against `run --print --policy-file`, per
ADR-0002's addendum.

## Assumed defaults

| ID | Assumed | Cost if wrong |
|----|---------|---------------|
| Q6 | Task ID is the satay run ID. | Small - a second identity field is additive if a task ever needs to be identified independently of any run. |
| Q7 | Episodic memory is its own SQLite store, never inside satay's own database. | Medium - migrating an established store's location later means a one-time data move, not a schema rewrite. |
| Q9 | The CLI blocks until a terminal state; there is no daemon mode yet. | Medium - a non-blocking `serve` mode is additive, not a redesign, since the workflow itself doesn't change. |
| Q11 | `LlmProvider` mirrors sibei-flow's own seam exactly. | Small - the interface is narrow and already proven in a sibling repo. |
| Q18 | No clarifying-question loop back to the operator in v1. | Medium - a stuck task just fails or does its best rather than pausing to ask, which is a real capability gap, not just a rough edge. |
| Q20 | Linux and macOS first-class, Windows best-effort, matching satay-runtime exactly. | Small - this project can never be more portable than the runtime underneath it. |

## Open risks

- **kopicode board KAN-987 landed (2026-08-23, kopicode PR #109)**, sooner than
  this plan expected. R2 and R6 can now be demonstrated beyond the read-only
  case. It shipped with a condition this plan didn't anticipate: kopicode
  ADR-0011 decision 4 asks the invoking orchestrator to provide containment
  for any policy-gated invocation, naming cuttlefish's own (not-yet-built)
  sandbox as the obligated party. Slice 1 uses the policy gate anyway, without
  the sandbox, as a deliberate, named exception on ADR-0002's existing
  trust-model reasoning - see that ADR's addendum and QUESTIONS.md Q25.
- **This project is satay-runtime's first real external consumer.** Nobody else in
  this suite has actually depended on satay as a library yet (sibei-flow's own port
  was deferred). Some of what breaks in slice 1 will be gaps in satay's own public
  surface, discovered here first, not bugs in this repository. The earliest slice
  is exactly where this would show up, which is the right place for it to.
- **Working memory's summarisation quality is unverified until real, long sessions
  exist.** A bounded LLM call distilling a journal window is a reasonable design,
  but whether the resulting handover is actually useful for continuing a task is
  an empirical question slice 1's own long-running test has to answer, not
  something this plan can settle on paper.
