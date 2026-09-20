# cuttlefish-crew: Slices

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

## V3: cuttlefish-crew — a pluggable, multi-project fleet

V1 and V2 proved one durable, sandboxed delegation to kopicode. V3 is the
pivot: cuttlefish becomes cuttlefish-crew, a fleet manager running teams of
coding sub-agents across many projects at once. See `docs/PLAN.md` for the
full problem/solution and `docs/QUESTIONS.md` Q28 onward for the decisions
behind it. Slices A, B, and C (both halves) are built; slices D-F are named
and real but not yet planned in this file - each gets its own build plan
once the slice before it ships and the interface it needs actually exists.

### Slice A: a pluggable agent backend, and the external rebrand

**Delivers:** `docs/PLAN.md`'s R0-R6.

**Build plan**

1. Define `cuttlefish.agents.AgentBackend` (a Protocol): invoke a delegation,
   parse the backend's own native output into one `DelegationOutcome`,
   declare/accept a policy file, report what containment/policy guarantees
   it can actually make (ADR-0005).
2. Move today's kopicode delegation logic behind it as `KopicodeBackend`,
   behavior preserved byte for byte: same NDJSON parsing, same KAN-987-
   descended policy file generation, same sandbox routing.
3. Generalize the episodic event schema to a backend-agnostic delegation
   outcome, forward-compatible with every event V1/V2 already wrote
   (ADR-0004's unmarshalling discipline, exercised for real).
4. Implement `ClaudeCodeBackend` against the same interface, wrapping
   headless Claude Code's own equivalent output mode.
5. Wire backend selection via `CUTTLEFISH_AGENT_BACKEND=kopicode|claude-code`,
   mirroring `CUTTLEFISH_SANDBOX`'s existing pattern.
6. External rebrand: repo README, CLI branding/help text, docs cross-links
   read as cuttlefish-crew. Python import path (`cuttlefish`) unchanged (Q30).
7. Record ADR-0005 (supersedes ADR-0003's single-backend assumption) and
   addenda to ADR-0001 (satay's steering primitive) and ADR-0002 (the
   multi-tenant trigger firing) reflecting the pivot's decisions.

**Demo:** the same `cuttlefish run "<task>"` delegation from V1/V2, run twice
against the same task with `CUTTLEFISH_AGENT_BACKEND` set to each of
`kopicode` and `claude-code` in turn, both landing a real edit through their
own real policy/sandbox path, both producing a journal readable through the
same `cuttlefish show` regardless of which backend ran it.

**Rests on assumptions:** Q29 (headless Claude Code is the specific second
backend chosen to prove pluggability) - if a live, credentialed Claude Code
CLI isn't available in this build's environment, the live end-to-end path is
named as an open gap the same way E2B's was in V2, not asserted from
unmocked-but-credential-less tests.

### Test plan

#### End-to-end

- The same task submitted via `CUTTLEFISH_AGENT_BACKEND=kopicode` and
  `CUTTLEFISH_AGENT_BACKEND=claude-code` both reach a terminal state and land
  a real edit, each through its own backend's real policy path.
- `cuttlefish show` on a task run under either backend renders a full,
  readable sequence with no backend-specific event type leaking into a
  human-facing summary meant to be backend-agnostic.

#### Integration

- Each backend's own native output stream (kopicode's NDJSON, headless
  Claude Code's own streaming shape) is parsed into the same
  `DelegationOutcome` shape by its own adapter.
- Existing sandbox routing (`CUTTLEFISH_SANDBOX=container|e2b|none`) and the
  declared per-task policy mechanism are exercised against both backends,
  not only kopicode.

#### Unit

- The `AgentBackend` Protocol is satisfied by both `KopicodeBackend` and
  `ClaudeCodeBackend` (a structural conformance test, not just type-checking).
- An event written by V1/V2's kopicode-specific schema still round-trips
  through the generalized backend-agnostic schema.

### Slice B: project/agent-scoped secrets management

**Delivers:** `docs/PLAN.md`'s R7-R9.

**Build plan**

1. `cuttlefish.secrets.SecretsStore` (ADR-0006): an encrypted-at-rest,
   project-scoped key/value store over its own SQLite file
   (`.cuttlefish/secrets.db`), Fernet-encrypted under an operator-held
   `CUTTLEFISH_SECRETS_KEY`. `resolve(project, names)` checks a project's
   own scope first, falling back to the shared scope (`SHARED_SCOPE`).
2. Extend `AgentBackend` (`cuttlefish.agents.backend`) with
   `CREDENTIAL_ENV_VARS` (each backend's own always-relevant credential
   names) and a `secrets: Mapping[str, str]` parameter on `delegate()`.
   `KopicodeBackend`/`ClaudeCodeBackend`'s own `_credential_envs` now prefer
   a resolved secret over `os.environ` for the same name, falling back to
   `os.environ` when the store has nothing — the exact seam Q34 named,
   replaced rather than bypassed.
3. Give the direct-host path parity with the sandboxed one:
   `run_kopicode`/`run_claude_code` gain an `env: Mapping[str, str] | None`
   parameter, merged as `{**os.environ, **env}` via the shared
   `cuttlefish.delegate.subprocess_env.merge_env` (`None`/empty still means
   exactly today's full inheritance).
4. Wire `project`/`secret_names` through `cuttlefish.tasks.delegate
   .delegate_to_agent_backend` (resolution happens *inside* this
   already-`side_effect=True` task — a decrypted value is a local variable
   here, never a satay task argument or return value) and
   `cuttlefish.workflow.run_task`'s `TaskInput`; record `project`/
   `secret_names` (names only) on `DelegationStarted`.
5. `cuttlefish run --project NAME --secret NAME` (repeatable), mirroring
   `--allow`'s shape; a declared name absent from both scopes is a
   config-time error (Q17), checked before the workflow starts. Seed the
   episodic journal's `Redactor` with the same resolved names so a leaked
   secret is still caught (a store-resolved value never touches
   `os.environ`, the redactor's own default lookup).
6. `cuttlefish secrets generate-key|set|get|list|delete` for managing the
   store directly — `set`'s value is prompted (hidden) or read from stdin,
   never a command-line argument.

**Demo:** `cuttlefish secrets generate-key`, then `cuttlefish secrets set
--project demo HUGGINGFACE_TOKEN` (piped or prompted), then `cuttlefish run
"<task>" --project demo --secret HUGGINGFACE_TOKEN` — the delegation's own
sandbox/subprocess carries `HUGGINGFACE_TOKEN` without it ever being
exported into the operator's shell. Declaring the same `--secret` with
`CUTTLEFISH_SECRETS_KEY` unset, or a name that was never set in either
scope, both fail closed with a clear config error before any task starts.

**Rests on assumptions:** Q38 (a project is a plain string, not a formal
entity yet) — if wrong, only the CLI's `--project` surface and the store's
own `scope` column meaning need to change; the store's schema doesn't.

### Test plan

#### End-to-end

- `cuttlefish secrets set` then `cuttlefish secrets get` round-trips a
  value for a project scope and, separately, the shared scope.
- `cuttlefish run --project X --secret NAME` with `NAME` set only in the
  shared scope still resolves it (fallback), and a project-scoped value of
  the same name wins over a shared one when both exist.
- `cuttlefish run --secret NAME` with `CUTTLEFISH_SECRETS_KEY` unset, or
  with `NAME` absent from both scopes, both exit with `EXIT_CONFIG_ERROR`
  before a workflow starts.

#### Integration

- `delegate_to_agent_backend` resolves `secret_names` unioned with the
  configured backend's own `CREDENTIAL_ENV_VARS`, scoped to the declared
  `project` — verified against a real `SecretsStore`, not a mock.
- A `DelegationStarted` event written before this slice (no `project`/
  `secret_names` keys in its encoded data) still decodes, defaulting to
  the one scope every task implicitly ran under then.

#### Unit

- `SecretsStore.set`/`get`/`delete`/`list_names`/`resolve` round-trip
  correctly, including scope fallback and cross-project isolation; the
  on-disk ciphertext never contains the plaintext.
- Each backend's `_credential_envs` prefers a resolved secret over
  `os.environ`, falls back to it when absent, and forwards any other
  declared secret verbatim.
- `merge_env(None)`/`merge_env({})` both return `None` (full inheritance
  preserved); a non-empty mapping merges over a copy of `os.environ`,
  overriding a same-named ambient value.

### Slice C: multi-agent team concurrency and steerable chat (both done)

**Delivers:** `docs/PLAN.md`'s R10-R12.

**Build plan (team-concurrency half, done)**

1. `cuttlefish.team.run_team` (ADR-0007): N named roles' delegations, run
   concurrently via `satay.gather(..., return_exceptions=True)`, sharing one
   `task_id` rather than one satay run per role — `start_child` can't hand a
   parent a child's run id before that child's first journal write, so a
   second identity scheme was rejected in favour of a `role` tag on every
   event a role writes.
2. `role: str | None = None` added to `TaskSubmitted`, `DelegationStarted`,
   `DelegationCompleted`, `DelegationRefused`, `DelegationFailed`,
   `HandoverWritten`, `TaskCompleted`, `TaskFailed` — defaulting to `None`,
   so every event written before this slice (and every plain `cuttlefish
   run` after it) decodes and behaves unchanged.
3. `cuttlefish.handover.maybe_handover` gained a `role` filter: the same
   algorithm, narrowed to one role's own tagged events (including `None`)
   so one role's journal can't force another's window closed early, or
   suppress its next handover.
4. `cuttlefish run-team --role NAME:TASK_TEXT` (repeatable, at least one
   required); `--root`/`--project`/`--allow`/`--secret`/`--token-budget`
   apply to every role uniformly this slice (no per-role policy
   differentiation yet).
5. `cuttlefish.cli`'s config resolution (backend/LLM/sandbox/secrets/
   redactor) factored into `_prepare_run`/`_PreparedRun`, shared by `run`
   and `run-team` rather than duplicated.

**Demo:** `cuttlefish run-team --role builder:"add a .gitignore entry"
--role reviewer:"check the .gitignore entry is correct"` — both roles'
delegations start together, journaled under one `task_id` with `role` on
every event; `cuttlefish show <task_id>` renders both interleaved.

**Verified live, 2026-09-20:**
- Real concurrency, not a declared-but-serial fan-out: two roles pointed at
  a deliberately-slow fake backend binary completed in one sleep's
  duration, not two.
- A real, accepted gap: two kopicode-backed roles sharing one `--root`
  collide on kopicode's own per-working-tree session lock — the second
  role's kopicode process starts concurrently, then immediately refuses
  ("another kopicode session is already running in this working tree").
  Not a bug to route around (Q44) — real concurrent *editing* needs
  separate checkouts per role, not attempted this slice.

**Rests on assumptions:** Q43 (real concurrency, not just a per-role
mechanism, was the right scope for this slice) and Q44 (naming the
kopicode-lock gap rather than building worktree isolation to close it) —
if wrong, a later slice needs to add per-role root/checkout support before
"a team" is useful against kopicode for anything that actually edits files.

### Test plan (team-concurrency half)

#### End-to-end

- `cuttlefish run-team` with two roles reaches a terminal state and prints
  a JSON result naming both roles' own outcomes.
- `cuttlefish show <task_id>` on a team renders every role's events,
  distinguishable by their own `role` field.
- No `--role` at all, or a duplicate role name, both exit
  `EXIT_CONFIG_ERROR` before any workflow starts.

#### Integration

- A real `run_team` execution (a deliberately-missing kopicode binary, the
  same no-mock discipline `test_delegate.py`/`test_workflow.py` already
  hold) journals every event under the failing role's own `role`, and a
  collected `satay.TaskFailedError` unwraps to the same reason string a
  direct `DelegationError` would have produced outside a team.
- Each role gets its own `HandoverWritten` once its own window crosses
  budget, independent of the other role's.

#### Unit

- `maybe_handover(..., role=...)` filters strictly to that role's own
  events (including `None`, the plain single-task case); one role's
  handover never suppresses another's.
- `_parse_roles` splits `NAME:TASK_TEXT` on the first `:`, rejects a
  missing `:`, an empty name/text, and a duplicate name.

### Slice C: steerable chat (done)

**Build plan**

1. satay `0.2.0` (`satay.control.run_app`, satay-runtime PR #101/#102,
   ADR-0046 there) closed the concrete gap that blocked this — `cuttlefish
   run` had no way to expose satay's own control API to anything outside the
   process (Q42). cuttlefish's own pin bumped to `satay[studio]==0.2.0` (the
   `[studio]` extra pulls in the FastAPI/uvicorn `satay.control.run_app`
   itself needs — ADR-0008's own consequence, not an opt-in extra of
   cuttlefish's own).
2. A design pass first (ADR-0008), not skipped: the original sketch ("race a
   short `wait_for_event` against normal delegation progress" via
   `satay.gather`) turned out to be an unverified composition of satay's own
   primitives — `wait_for_event`'s `WorkflowParked` unwinds the *whole*
   workflow drive (a `BaseException`, handled only at the outermost per-run
   loop), not one `gather` member, and neither kopicode's nor headless
   Claude Code's headless surface accepts input after it starts anyway
   (verified from source — a single argv positional, no stdin wiring).
   ADR-0008 designed the buildable alternative instead: redirect at the
   boundary between delegation rounds.
3. `SteeringMessage(text, role)` (`cuttlefish.episodic.events`) — one
   dataclass doing two jobs: satay's own wire payload type
   (`wait_for_event`/`send_event` derive their inbox key's type name from
   its `module.qualname`) and the episodic event journaled the moment a
   round consumes one.
4. `run_task`/`run_team` gain `steerable: bool = False` (default off, byte-
   for-byte unchanged when unset) and become a loop of rounds: after each
   round's outcome is journaled, one plain, sequential `wait_for_event(...,
   timeout=DEFAULT_STEERING_GRACE_SECONDS)` decides whether to fold a queued
   message into one more round (`cuttlefish.steering.compose_steered_text`)
   or finalize with that round's own outcome. `run_team`'s own poll happens
   *after* its `satay.gather` resolves, sequentially per role, never nested
   inside one of that gather's members (the same unverified-composition risk
   step 2 found). A `DelegationError` (an infra-level failure, not a
   recorded `DelegationOutcome`) is never steered around, either workflow.
5. `cuttlefish.steering`: the key scheme (`task_id`, or `task_id:role` for a
   team role), the pointer file (`.cuttlefish/steering/<task-id>.json`,
   written by `run --steerable`/`run-team --steerable`, removed on exit),
   and `send_steering_message` — a synchronous HTTP client (`urllib.request`,
   no new dependency) POSTing to satay's own `POST /runs/{run_id}/events`.
6. `cuttlefish run --steerable` / `run-team --steerable` open
   `satay.control.run_app()` instead of a bare `satay.run_app()`, print
   `{"task_id": ..., "steering": {"base_url": ..., "token": ...}}`, and
   write the pointer file. `cuttlefish steer <task-id> "<message>" [--role
   NAME]` reads it and delivers.

**Demo:** `cuttlefish run --steerable "add a .gitignore entry"` in one
terminal; `cuttlefish steer <task-id> "actually add a .dockerignore
instead"` in another while the first round is still running — the task
starts a second round with the message folded into its prompt, visible in
`cuttlefish show <task-id>` as a `SteeringMessage` event between two
`DelegationStarted` events.

**Verified live, 2026-09-21**, against the real kopicode binary (a real,
rejected-but-uncharged network round trip so kopicode reaches a genuine
`session_ended` rather than failing before ever opening a session): a
message sent mid-round starts a fresh round with it folded into the prompt
for both a plain task and a team role; a role nobody steers finalizes after
exactly one round, untouched by another role being steered.

**Rests on assumptions:** the round-boundary redirect (not instant, bounded
by however long the round in flight takes) satisfies R12's "can redirect a
still-running delegation's work" as written — if an operator's real usage
needs faster-than-round-boundary responsiveness, that's new information this
slice's own design pass didn't have, not a bug in it.

### Slices D-F: not yet fully planned

Named and real, sketched in `docs/PLAN.md`'s Open risks and
`docs/QUESTIONS.md` Q28-Q44, but none has its own build plan yet.

- **Slice D - the dashboard**: a game-like pixel-art virtual office per
  project, plus a zoomed-out portfolio view across many projects.
- **Slice E - runners and hosting**: a registered-runner abstraction (an
  always-on operator machine, or a cuttlefish-crew-provisioned deployment)
  fronted by a stable URL, closing the "view a real demo without being at
  the machine" gap. Needs satay-runtime's Postgres/multi-worker milestone
  (satay-runtime#100) to run many projects' workflows concurrently.
- **Slice F - meetings, explicitly last**: agent-requested or on-demand
  meetings, TTS + an avatar presenting project status over existing
  video-call infrastructure cuttlefish-crew facilitates rather than builds.
