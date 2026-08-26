# cuttlefish-agent: Slices

Vertical increments. Each ends in something you can demonstrate. Slice 1 confronts
the riskiest unknown: whether a satay-workflow core loop can actually survive a
crash mid-delegation and resume correctly, since everything else in this plan rests
on that being true.

## V1: A durable, resumable delegation to kopicode

**Delivers:** R0, R1, R2 (partial - see below), R3, R4, R5, R6, R7

**Build plan**

1. Scaffold the package (`uv init`, ruff, mypy `--strict`, pytest, matching
   satay-runtime's own toolchain), pin `satay==0.1.0`.
2. Define the episodic event types: a tagged union, versioned, with a redactor for
   known secret values at write time (ADR-0004). Get this right first - everything
   else appends to it.
3. Write the `@satay.workflow` core loop and its `@satay.task` boundaries: one task
   per LLM call, one task for the kopicode delegation (ADR-0001).
4. Write the kopicode delegation task against kopicode's **current** headless
   behaviour: shell out to `kopicode run --print`, parse its NDJSON stream, handle
   its present-day unconditional refusal as a real, journaled failure (ADR-0003).
5. Write the working-memory handover: a token-budget check, one bounded LLM call
   over the recent episodic window at the threshold, written back as an episodic
   event (ADR-0004).
6. Write the CLI (`cuttlefish run "<task>"`, `cuttlefish show <task-id>`).
7. Write the crash-recovery test using satay's `FaultInjector`: kill the process
   after a chosen journal event, resume, assert the same terminal state and no
   duplicated delegation call.
8. kopicode board KAN-987 has shipped (2026-08-23, kopicode PR #109,
   `internal/permission.AllowlistPolicy` plus `run --print --policy-file`).
   Extend the delegation task to write a policy file (a `root` scoped to the
   task's scratch checkout, an `allow` list built from the configured
   allowlist) and pass `--policy-file`, demonstrating an actual file edit
   landing through it - this is the part of R2 and R6 that couldn't be proven
   before. Note: kopicode ADR-0011 decision 4 asks the invoking orchestrator
   to provide process/container containment for any policy-gated invocation;
   slice 1 does this without one, a deliberate, named exception - see
   ADR-0002's addendum and Q25.

**Demo:** `cuttlefish run "add a .gitignore entry for build artifacts"` against a
scratch checkout, kill the process mid-run with `kill -9`, run it again, watch it
resume and finish. `cuttlefish show <task-id>` prints the whole thing afterward:
what was asked, what was delegated, what kopicode did, in order, from the journal.

**Rests on assumptions:** Q9 (the CLI blocks rather than running as a daemon) - if
wrong, the demo still works, but a "fire and forget" story needs a second surface
later. Q18 (no clarifying-question loop) - if wrong, an ambiguous task just does
its best or fails, rather than pausing to ask, which is a real gap a real operator
will notice quickly.

### Test plan

#### End-to-end

- A real task submitted via the CLI reaches a terminal state and prints a JSON
  result.
- Killing the process mid-delegation and restarting resumes to the same terminal
  state without a second kopicode invocation for the same call.
- `cuttlefish show` on a completed task renders the full sequence of what
  happened, matching the episodic journal exactly.
- A task requiring an action kopicode currently refuses headless (before KAN-987
  lands) surfaces as a clear, journaled failure, not a hang or a silent no-op.
- Once KAN-987 lands: a task that edits a file inside the scratch checkout's
  allowlisted scope actually lands the edit.

#### Integration

- The delegation task's NDJSON parser handles a real `run --print` stream,
  including a mid-stream cancellation event.
- A secret value (a fake API key) placed in a tool result is absent from the
  written episodic journal file, byte for byte.
- The working-memory handover fires at the configured token threshold and the
  resulting summary event is itself readable from the journal.

#### Unit

- Each episodic event type round-trips through its serialisation.
- The redactor strips every declared secret pattern and nothing else.
- The delegation task's idempotency key is stable across a retry of the same
  logical call.

## V2: Real containment and a general policy

**Delivers:** the sandbox package (ADR-0002), a general (non-hardcoded) policy
mechanism for the kopicode delegation, replacing V1's fixed allowlist once there's
a second real policy to compare it against.

**Build plan**

1. Build `cuttlefish/sandbox`: the create/exec/snapshot/destroy interface, one
   E2B-backed implementation. A second, container-backed implementation was
   added against the same interface once it turned out E2B needed a live
   account this project didn't have yet, and kopicode's own contract permits
   container containment as well as a microVM's - see ADR-0002's 2026-08-26
   addendum and `docs/QUESTIONS.md` Q27.
2. Route the kopicode delegation through it instead of a bare scratch checkout.
   Landed against the container backend specifically (`CUTTLEFISH_SANDBOX=container`,
   opt-in - unconfigured still means V1's original direct-host behaviour, not a
   default this project widened quietly). The scratch checkout, the kopicode
   binary, and the policy file are bind-mounted in rather than copied, so a real
   edit lands on the host exactly where V1 always put it. Two real gaps only
   showed up running this live, not from reasoning about the design up front: a
   container doesn't inherit the host's environment, so kopicode's own
   model-provider credential has to be forwarded explicitly; and a bare base
   image (verified against a few candidates) typically ships no CA bundle at
   all, so an outbound HTTPS call fails TLS verification unless one is
   provided - fixed by reusing whatever CA bundle the docker daemon's own host
   already has, since anything that can `docker pull` already needs one.
3. Generalise V1's hardcoded allowlist into a declared, per-task policy, informed
   by whatever V1's fixed allowlist turned out to actually need. Landed as a
   repeatable `cuttlefish run --allow "<shell command>"` flag.

**Demo:** the same delegation from V1, now running inside a container sandbox
rather than a bare scratch checkout, with the policy declared per task rather
than fixed in code. (E2B remains the backend for the same demo once there's a
live account to run it against - the interface doesn't care which backend a
given task uses.)

**Rests on assumptions:** ADR-0002's trigger condition (multi-tenant exposure, or
task input the operator didn't author themselves) has actually occurred by the
time this slice is scheduled - if it hasn't, this slice is speculative work ahead
of a real need, the same trap kopicode's own ADR-0008 warns against.

### Test plan

#### End-to-end

- A delegation that would escape a bare scratch checkout (writes outside the
  intended directory, or opens an outbound network connection the task didn't
  need) is contained by the sandbox and doesn't touch the host.

#### Integration

- The sandbox interface's create/exec/snapshot/destroy cycle is exercised against
  a real E2B account in CI, gated behind a cost-bearing test tag the same way
  kopicode gates its own paid `make bench`.

#### Unit

- The policy's allow/deny decision is exercised against a table of declared
  policies and requests, independent of the sandbox itself.
