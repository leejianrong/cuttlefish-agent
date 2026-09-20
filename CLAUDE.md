# CLAUDE.md — agent brief for cuttlefish-crew

cuttlefish-crew is pivoting from a single-task supervisor into a fleet
manager for teams of coding sub-agents across many software projects,
dashboard-observable, with automated context handover and a hosting story
for viewing a real demo remotely. Built on
[satay-runtime](https://github.com/leejianrong/satay-runtime) for durable
workflow execution, delegating coding work through a pluggable
`AgentBackend` seam —
[kopicode](https://github.com/leejianrong/kopicode) is the reference
backend, headless Claude Code the second. Python, `uv`, `ruff`,
`mypy --strict`, `pytest` — the same toolchain conventions as satay-runtime,
since this project depends on it directly.

## Trust the code over the docs

`docs/` describes the intended system; where the two disagree, the code is
the truth — `ls src/cuttlefish/`, `git log --oneline`, and a module's own
doc comment all beat a paragraph here.

- [`docs/PLAN.md`](docs/PLAN.md) — the current problem, scope, and shape
  (the cuttlefish-crew pivot direction, built on top of V1/V2's original MVP)
- [`docs/adr/`](docs/adr/) — why each load-bearing decision was made, 0001–0007
- [`docs/SLICES.md`](docs/SLICES.md) — the build order this was built against
- [`docs/QUESTIONS.md`](docs/QUESTIONS.md) — every decision, who made it, and
  where it landed, including gaps a live run surfaced after the fact
- Pandan board `cuttlefish-agent` (key `CUT`) — build-plan progress as
  epics/stories

## What's built

V1, V2 (a durable, sandboxed kopicode delegation), slice A (the pluggable
`AgentBackend` seam — `KopicodeBackend` and `ClaudeCodeBackend`, selected via
`CUTTLEFISH_AGENT_BACKEND`), slice B (`cuttlefish.secrets.SecretsStore` —
an encrypted-at-rest, project-scoped secrets store injected through each
backend's own `_credential_envs`), and slice C's team-concurrency half
(`cuttlefish.team.run_team` — N named roles delegating concurrently via
`satay.gather`, `cuttlefish run-team --role NAME:TASK_TEXT`) are complete
and merged; `make ci` is green on `main`. Slice C's steering half is
unblocked (satay `0.2.0` ships `satay.control.run_app`, satay-runtime PR
#101/#102) but not yet built here. Start reading the code at
`cuttlefish/workflow.py` (the single-task core loop),
`cuttlefish/team.py` (the multi-role loop), `cuttlefish/agents/` (the
backend seam), and `cuttlefish/secrets/` (the secrets store) — each
module's own doc comment explains why it exists, not a list here.
Live-verification history and real bugs a live run found and fixed are in
each PR's own description and `docs/QUESTIONS.md`, not repeated here.

## Known, accepted gaps — don't re-litigate

- `ClaudeCodeBackend`'s sandboxed path only works for an operator
  authenticated via `ANTHROPIC_API_KEY`, not Claude Code's own OAuth login.
  `docs/QUESTIONS.md` Q37.
- Its declared-allowlist-to-`--allowedTools` mapping is an honest
  approximation, not full parity with kopicode's KAN-987 policy gate.
  `docs/QUESTIONS.md` Q36.
- satay-runtime is one process, one writer — no two *projects'* cuttlefish
  tasks run concurrently yet (one project's own team of roles does, via
  `satay.gather`, needing no multi-worker capability at all). satay-runtime's
  own roadmap now follows cuttlefish-crew's needs rather than being a fixed
  dependency; a concrete need gets filed — and, as of slice C, actually
  built — there, not worked around here. `docs/QUESTIONS.md` Q33, Q42.
- Two kopicode-backed team roles sharing one `--root` collide on kopicode's
  own per-working-tree session lock — real concurrent *editing* needs
  separate checkouts per role, not built yet. Not a bug; kopicode's lock is
  correctly guarding against two agents editing one uncommitted working
  tree at once. `docs/QUESTIONS.md` Q44.
- Secrets are injected directly, never brokered — the agent process itself
  still holds every secret it's given in the clear, inside its own sandbox
  or subprocess. A credential-broker/proxy is real future work, deliberately
  deferred. `docs/QUESTIONS.md` Q34, ADR-0006.
- A project's secrets scope is a plain string (`--project NAME`), not a
  formal `Project` entity — that's slice D's job. `docs/QUESTIONS.md` Q38.

## Workflow conventions

- `main` is PR-only. Branch per slice part: `git switch -c feat/<slice>-<part>`
  off `origin/main`, then open a PR. `make ci` green before merging.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- `make check` (lint + `mypy --strict`), `make test` (fast, unit-only),
  `make ci` (the full suite `make test-all` gates on). CI additionally
  builds kopicode from source so the delegation's integration tests run
  against the real binary, not a mock.

## Boundaries that must not be crossed

These follow directly from the ADRs. Hold them without re-litigating them here.

- **The core loop is a satay workflow from the first commit that runs a
  task**, not an ordinary function made durable later. ADR-0001.
- **Episodic memory is its own SQLite store**, never a table inside satay's
  own `.satay/` database. ADR-0004.
- **No parallel transcript.** Everything a person or another tool reads back
  is derived from the episodic journal. ADR-0004.
- **The sandbox stays an internal package, not a second product**, until a
  real second consumer or concrete reason to spin it out exists. ADR-0002.
- **No new protocol for any given backend.** Each `AgentBackend` wraps its
  own tool's existing headless surface as it exists; cuttlefish-crew
  normalises on its own side (`DelegationOutcome`), never inventing a shared
  wire format between backends. ADR-0003, ADR-0005.
- **Secrets are redacted from the episodic journal at write time**, not read
  time.
- **A project-scoped secret's decrypted value never becomes a satay task
  argument or return value.** `cuttlefish.secrets.SecretsStore.resolve` is
  only ever called *inside* the already-side-effecting delegation task; the
  result is a local variable handed straight to `backend.delegate()`, never
  returned or passed to another task. ADR-0006.

## Secrets

- **Never read or open `.env`.** It holds the real `OPENROUTER_API_KEY` for
  this repo. Refer to `.env.example` instead — the committed template with
  no real values.
- **Never read or open `.cuttlefish/secrets.db`.** It's encrypted at rest,
  but still holds every project's real secrets; use `cuttlefish secrets
  get/list` instead. Never log or print `CUTTLEFISH_SECRETS_KEY` itself —
  losing it is equivalent to losing every secret it protects.
