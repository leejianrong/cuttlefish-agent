# cuttlefish-crew: Plan

Status: agreed and delivered - slice A (pluggable agent backend + rename,
PR #21) and slice B (project/agent-scoped secrets management, ADR-0006) are
both complete and merged. Supersedes the single-task-MVP framing this
document held through V1/V2 (both complete, both merged to `main` - see
`CLAUDE.md`'s "What's built" for that history, which stays true and is not
being redone, only built on). Next up per `docs/SLICES.md`: slice C,
multi-agent handover and steerable chat.

## Problem

V1/V2 proved the mechanism this project bet on: a `@satay.workflow` core loop
can survive a crash mid-delegation and resume correctly, and a single
delegated coding task, gated by a real policy and (optionally) a real
sandbox, can run unattended end to end against a live kopicode binary. That
was the riskiest unknown, and it held up.

What it didn't touch is the actual, lived pain of running coding agents day
to day: babysitting a single agent's context window (watching it bloat, then
manually clearing or starting a new session before it does), and babysitting
its *output* - the UI, the demo, the actual user-facing behavior - because a
green test suite doesn't tell you the product is right. Both of those are
single-agent, single-project problems, and they don't go away just because
the delegation survives a crash. Worse, they compound the moment there's more
than one project worth running unattended at once: there's no single place
to see what every project's agents are doing, whether any of them are stuck
on a context ceiling, or whether what they built actually looks right,
without being at the keyboard for each one.

## Solution

cuttlefish-crew runs a small team of coding sub-agents (roughly three) per
software project, across as many projects as the operator is running at
once. Each project's team has functional roles (e.g. a builder, a reviewer,
an ops/demo-checker) and a distinct personality/voice per agent, so the
record of what happened reads as a team, not a wall of uniform log lines.
Context handover across a long session is automatic, triggered on a
token-budget threshold exactly like V1's existing mechanism (ADR-0004),
generalized to run per-agent across a team instead of once per task. The
operator oversees every project's team from one dashboard, can click into a
running agent and steer its work directly rather than only reading its
history, and can view a running project's actual demo/UI remotely without
being at the machine it's running on - either through a tunnel to an
always-on machine the operator controls, or through cuttlefish-crew
provisioning a hosted, reachable deployment itself.

This milestone (slice A) builds none of that observable surface yet. It
builds the one thing everything else depends on: the coding sub-agent is no
longer hardcoded to be kopicode. A generic backend interface is introduced,
kopicode becomes its first implementation with no behavior change, and a
second backend (headless Claude Code) is implemented against the same
interface to prove the abstraction is real rather than aspirational -
directly motivated by the fact that Claude Code, not kopicode, is the agent
the operator actually babysits today.

## Users and actors

- **The operator** (primary). Runs cuttlefish-crew, configures which
  projects it oversees and what each project's team may delegate, and holds
  the credentials it uses. Was the sole intended user through V1/V2; this
  project is now explicitly meant to grow toward other operators running
  their own teams, which is a real scope expansion Q28 and ADR-0002's
  2026-09-20 addendum need to reckon with (multi-tenancy, isolation
  between operators), not something this milestone builds.
- **A project's sub-agent team** (new framing, not built this milestone).
  Roughly three agents per project, each with a functional role and a
  personality. Not a distinct trust tier from the operator's own
  configuration - same posture ADR-0002/Q23 already established for a
  single delegation, extended to a team.
- **A coding agent backend** (a dependency, pluggable). kopicode remains the
  reference implementation; a second, headless-Claude-Code-backed
  implementation is this milestone's proof that the interface isn't shaped
  around kopicode by accident. Neither backend is a distinct trust tier;
  both run inside whatever sandbox/policy the operator's configuration
  already grants (ADR-0002, KAN-987's descendant policy mechanism).
- **satay-runtime** (a co-evolving dependency, not a fixed one, as of
  2026-09-20). Previously treated as an external library this project
  tracked at a pinned version and worked around. The operator has since said
  satay's own roadmap should now be driven by cuttlefish-crew's needs -
  concrete asks are filed as satay-runtime issues, not worked around inside
  this repo. See Open risks.
- **Runners** (named here, not built until a later slice). A place that can
  run a project's deployment and expose it - the operator's own machine, a
  homelab box, or eventually cuttlefish-crew-provisioned compute. Out of
  scope for this milestone entirely; named so the backend interface this
  milestone builds doesn't accidentally foreclose it.

## Scope

**In this milestone.**

- A generic `AgentBackend` interface that a coding delegation runs through,
  replacing today's kopicode-hardcoded call site inside `cuttlefish.delegate`.
- `kopicode` reimplemented as one `AgentBackend` implementation, with zero
  behavior regression from V1/V2 - the same NDJSON parsing, the same policy
  file generation, the same sandbox routing, now living behind the interface
  instead of being the only thing that exists.
- A second `AgentBackend` implementation wrapping headless Claude Code,
  capable of running at least one real delegation end to end, proving the
  interface generalizes past kopicode's own shape.
- A backend-agnostic episodic event representation for a delegation outcome,
  forward-compatible with events V1/V2 already wrote (ADR-0004's
  unmarshalling discipline - an unrecognized or superseded event shape still
  round-trips, it isn't dropped).
- The external rebrand: repository name, README, CLI branding/help text, and
  docs cross-links read as **cuttlefish-crew**. The Python package import
  path (`cuttlefish`, `src/cuttlefish`, `pyproject.toml`'s `name =
  "cuttlefish"`) is unchanged (Q30).
- Superseding or amending ADRs for ADR-0002 (the product-ambition trigger it
  named has now fired) and ADR-0003 ("no new protocol, wrap kopicode as it
  exists" - now extended to "no new protocol *between* backends either," but
  the single-protocol assumption itself is superseded), recorded rather than
  left silently stale.
- **Slice B, project/agent-scoped secrets management (ADR-0006, Q34):** an
  encrypted-at-rest secrets store (`cuttlefish.secrets.SecretsStore`,
  `.cuttlefish/secrets.db`), scoped per project with an explicit shared
  scope (`SHARED_SCOPE`) for a value like a personal OpenRouter key. Both
  `KopicodeBackend`/`ClaudeCodeBackend`'s own `_credential_envs` now resolve
  a name from the store before falling back to `os.environ`, and forward it
  into a sandbox (`SandboxSpec.envs`) or a direct-host subprocess (a new
  `env` parameter on `run_kopicode`/`run_claude_code`) alike - the seam
  named in Q34 as "the thing to replace, not bypass" now goes through the
  store first, ambient environment second, rather than only ever reading
  `os.environ`. An operator declares which named secrets a task may read via
  `cuttlefish run --project NAME --secret NAME` (repeatable), the same shape
  `--allow` already established; a declared name absent from both scopes is
  a config-time error (Q17's fail-closed posture), not a silent no-op. The
  episodic journal's redactor is seeded with the same resolved names so a
  secret that leaks back into a tool result still gets caught, and no
  decrypted value ever crosses a satay task boundary (ADR-0006's own
  "no satay-journaled plaintext" section). No credential-broker/proxy - that
  remains explicitly deferred (Q34), unattempted this slice.

**Out.**

- Automated context handover redesigned for a multi-agent team (slice C, was
  B). V1's existing per-task handover (ADR-0004) keeps working unmodified;
  making it work sensibly across three agents sharing or diverging on
  context is explicitly a later slice's problem, not this one's.
- Steerable chat - a human redirecting a running agent's work mid-task.
  Confirmed buildable on satay's existing `wait_for_event`/`send_event`
  primitive (see Open risks), but the workflow-shape work to actually use it
  is slice C.
- Any dashboard, office visualization, or UI of any kind (slice D, was C).
  This milestone has no observable surface beyond the existing CLI.
- The runner/hosting abstraction and remote demo viewing (slice E, was D).
- Actually running more than one project's delegation at a time, or any
  scheduling/job-queue work that implies. This milestone still proves the
  backend abstraction on the same one-task-at-a-time shape V1/V2 already
  have; "many projects, many teams, concurrently" is slice C/D's problem and,
  underneath that, satay-runtime's own multi-worker milestone (see Open
  risks).
- The meetings-with-avatar feature. Explicitly deferred to last, after
  everything else in this roadmap, by the operator's own instruction.
- Any actual multi-tenancy, auth, or isolation-between-operators
  implementation. "Building toward a product" is a design constraint
  ADR-0002's 2026-09-20 addendum has to acknowledge, not something built in
  code yet.
- Any change to satay-runtime's own codebase. This milestone's backend
  abstraction doesn't need new satay capability; where a later slice will,
  it's filed as a satay-runtime issue for that project's own roadmap, not
  built inside this repo.
- A credential-broker/proxy (the agent never holds a raw secret at all, only
  a scoped local proxy does) - explicitly deferred by Q34's own reasoning,
  real future work once slice B's simpler direct-injection version's gaps
  are concretely felt, not attempted this slice (ADR-0006).
- A formal `Project` entity. Slice B's `--project NAME` is a plain string
  scope, defaulting to `--root`'s own directory name - real, but provisional
  (docs/QUESTIONS.md Q38); a first-class `Project` with its own identity is
  slice D's (the dashboard's) job, not this one's.

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | A coding subtask is delegated through a generic `AgentBackend` interface, not a kopicode-hardcoded call site. | Core goal |
| R1 | kopicode continues to work exactly as it does today behind the new interface - same NDJSON parsing, same policy file generation, same sandbox routing - zero behavior regression from V1/V2. | Must-have |
| R2 | A second backend (headless Claude Code) is implemented against the same interface and completes at least one real delegation end to end. | Must-have |
| R3 | The episodic event schema represents a backend-agnostic delegation outcome, forward-compatible with events V1/V2 already wrote. | Must-have |
| R4 | The repo/product's external surface (README, CLI help text/branding, docs cross-links) reads as cuttlefish-crew; the Python package import path (`cuttlefish`) is unchanged. | Must-have |
| R5 | ADR-0002 and ADR-0003 have superseding or amending ADRs recorded reflecting the pluggable-backend and product-ambition decisions. | Must-have |
| R6 | Existing sandbox routing (`CUTTLEFISH_SANDBOX=container\|e2b\|none`) and the declared per-task policy mechanism work per-backend, not only for kopicode. | Must-have |
| R7 | A project/agent-scoped secrets store is encrypted at rest, scoped per project with an explicit shared scope, and an operator never configuring it gets today's exact V1/V2/slice-A behaviour unchanged. | Must-have (slice B) |
| R8 | A declared secret is injected into both a sandboxed and a direct-host delegation, for both backends, through the same `_credential_envs` seam each backend already had - not a bolted-on second channel. | Must-have (slice B) |
| R9 | A store-resolved secret value never becomes a satay-journaled task argument or return value, and the episodic journal's own redactor still catches it if it leaks back into a tool result. | Must-have (slice B) |

## Shape

| Part | Mechanism | ADR |
|------|-----------|-----|
| S1 | `AgentBackend` protocol (invoke, parse its own native stream into one `DelegationOutcome`, declare/accept a policy file) replacing the kopicode-specific call inside `cuttlefish.delegate` | forthcoming, supersedes ADR-0003 |
| S2 | `KopicodeBackend` - today's delegation logic moved behind the interface, behavior preserved byte for byte | ADR-0003 (superseded), forthcoming |
| S3 | `ClaudeCodeBackend` - headless Claude Code wrapped the same way, proving the interface isn't kopicode-shaped by accident | forthcoming |
| S4 | Backend-agnostic episodic event types for a delegation outcome, versioned per ADR-0004's forward-compatible unmarshalling | ADR-0004 |
| S5 | External rebrand: repo name, README, CLI branding/help text, docs cross-links -> cuttlefish-crew; package import path (`cuttlefish`) unchanged | - |
| S6 | An addendum to ADR-0002 (the multi-tenant trigger it named has fired) and a superseding ADR-0005 for ADR-0003 (multi-backend delegation) | ADR-0002 addendum, ADR-0005 |
| S7 | `cuttlefish.secrets.SecretsStore` - an encrypted-at-rest, project-scoped key/value store (`.cuttlefish/secrets.db`), plus `cuttlefish secrets set/get/list/delete/generate-key` and `cuttlefish run --project/--secret` | ADR-0006 |
| S8 | Each `AgentBackend`'s own `_credential_envs`/`CREDENTIAL_ENV_VARS` resolve a name from the store before `os.environ`; `run_kopicode`/`run_claude_code` gain an `env` parameter so a direct-host delegation gets the same injection a sandboxed one already had | ADR-0006 |

## Affordances

**Non-UI.**

| Affordance | Kind | Wires to |
|------------|------|----------|
| `CUTTLEFISH_AGENT_BACKEND=kopicode\|claude-code` | Config | Selects which `AgentBackend` implementation the delegation task routes through, the same pattern `CUTTLEFISH_SANDBOX` already established |
| `cuttlefish run "<task>"` / `cuttlefish show <task-id>` | CLI commands | Unchanged in shape this milestone - the dashboard is slice C, not this one |
| `CUTTLEFISH_SECRETS_KEY` | Config | Opt-in, mirroring `CUTTLEFISH_SANDBOX`'s posture - unset means no `SecretsStore` at all, every credential still resolved from `os.environ` |
| `cuttlefish run --project NAME --secret NAME` | CLI flags | Declares this task's secrets scope and which named secrets (beyond a backend's own ambient credential names) it may read (ADR-0006) |
| `cuttlefish secrets generate-key\|set\|get\|list\|delete` | CLI commands | Manages the store directly - the only way to actually populate it |

## Implementation decisions

The interface's job is to normalize every backend's outcome to the one
`DelegationOutcome` shape this project already defines, not to invent a
shared wire format between backends. Each backend keeps speaking its own
native CLI language (kopicode's NDJSON stream over `run --print`, whatever
headless Claude Code's own streaming shape turns out to be) - this extends
ADR-0003's original "no new protocol" discipline rather than abandoning it:
there's still no new protocol invented *for* any given backend, there's just
now more than one backend cuttlefish-crew knows how to talk to.

Sandbox routing and the declared per-task policy mechanism already live one
layer above any specific backend (`cuttlefish.sandbox`, `cuttlefish.tasks.
delegate`). Making them work per-backend should be an additive parameter to
that existing plumbing, not a fork of it - a second sandbox backend was
already added this way in V2 (ADR-0002's 2026-08-26 addendum), and a second
agent backend should follow the identical shape: one more implementation of
an interface this project already owns.

Backend heterogeneity is real and shouldn't be hidden: kopicode's policy
gate (KAN-987's descendant) is purpose-built and mature; headless Claude
Code's own permission model won't necessarily map onto the same declared-
allowlist shape. The interface should surface that difference honestly
(e.g. a backend reports what containment/policy guarantees it can actually
make) rather than force every backend to pretend to the same guarantees
kopicode happens to provide.

## Testing approach

Same discipline V1/V2 already hold: test against real binaries, not mocks,
for whichever backends have a real credential and binary available in the
build environment. If headless Claude Code isn't available as a live,
credentialed binary in this build's environment the way E2B wasn't in V2,
say so plainly rather than asserting the path from unmocked-but-credential-
less tests - unit- and integration-test the backend against its documented
contract, and name the live end-to-end path as an open gap until it's
actually run, the same honesty V2's `CLAUDE.md` entry already models for
E2B.

## Assumed defaults

| ID | Assumed | Cost if wrong |
|----|---------|---------------|
| Q29 | The second backend proving pluggability is headless Claude Code, not a third tool. | Small - the interface doesn't care which second implementation proves it; swapping which tool goes second is additive. |
| Q30 | The Python package import path stays `cuttlefish` while the repo/product/CLI branding become cuttlefish-crew externally. | Small now; if this project is ever published as an installable library under its own name, an import-path/product-name mismatch could confuse a new contributor - accepted for now, revisit if that happens. |
| Q38 | A project's secrets scope is a plain string (`--project NAME`, defaulting to `--root`'s directory name) rather than waiting for a formal `Project` entity. | Small - a real `Project` entity (slice D) can be introduced later without changing the store's own schema (`scope` is already just a string); the cost is only that two different root paths for "the same" project must currently be named consistently by the operator, not inferred. |

## Open risks

- **satay-runtime is no longer treated as a fixed external dependency.** As
  of 2026-09-20 the operator has said satay's own roadmap should be driven
  by cuttlefish-crew's needs going forward. Three concrete asks are already
  filed against it rather than worked around here: satay-runtime#98 (a live
  query primitive for in-progress workflow state), satay-runtime#99
  (document/example the `wait_for_event`/`send_event` pattern for external
  steering), and satay-runtime#100 (prioritize the Postgres Store +
  multi-worker milestone ADR-0025 already earmarks). None of these block
  this milestone; slice B needs #98/#99, and "many projects concurrently"
  eventually needs #100.
- **This pivot is bigger than slices A and B alone.** Slice C (multi-agent
  handover + steerable chat), slice D (a dashboard, sketched as a
  game-like pixel-art virtual office with a zoomed-out portfolio view for
  scale), slice E (the runner/hosting abstraction unifying "tunnel to an
  always-on machine" and "cuttlefish-crew provisions a hosted deployment
  itself"), and a deferred, explicitly-last slice F (agent-initiated
  meetings, TTS + avatar, facilitated through existing video-call
  infrastructure rather than built from scratch) are all real, discussed,
  and intended - slice B (ADR-0006) is now done: an encrypted-at-rest
  secrets store, scoped per project with a shared fallback, injected
  through each backend's own `_credential_envs` seam, no credential
  broker/proxy yet. Slice B was inserted after slice A was first scoped,
  once it became clear that multiple projects each needing distinct,
  isolated credentials is a slice-A-adjacent pain, not a slice-E-hosting-only
  one (Q34).
- **The product-ambition decision fires one of ADR-0002's two named
  triggers, not the one about spinning the sandbox out as its own
  product.** ADR-0002 named two independent triggers: whether the sandbox
  becomes a separate product (ungated - no second real consumer of the
  interface itself exists, so this stays internal), and whether real
  containment is *necessary* (gated on multi-tenant exposure or untrusted
  task input). The operator has now said cuttlefish-crew is being built
  toward a product for other operators, not only personal use - that's the
  second trigger firing for real, addressed in ADR-0002's 2026-09-20
  addendum. It doesn't add new containment work (V2 already built real
  sandboxing before this trigger fired, for a different reason); it means
  the "one operator, their own machine" trust-model framing ADR-0002 uses
  throughout stops being the operating assumption, and isolation *between*
  operators becomes a real design question for whichever slice builds
  multi-operator hosting (slice E).
- **Backend heterogeneity may surface a real capability gap, not just an
  interface-design question.** If headless Claude Code (or any future
  backend) can't make the same containment/policy guarantees kopicode's
  KAN-987 gate makes, R6 may not be satisfiable uniformly across backends -
  an honest per-backend capability report, not a forced uniform contract, is
  the planned answer, but this is unverified until a second backend is
  actually built against a real policy requirement.
