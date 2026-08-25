# CLAUDE.md - agent brief for cuttlefish-agent

cuttlefish is a long-running, unattended task assistant, built on
[satay-runtime](https://github.com/leejianrong/satay-runtime) for durability and
delegating coding subtasks to [kopicode](https://github.com/leejianrong/kopicode)
over its existing headless interface. Python, `uv`, `ruff`, `mypy --strict`,
`pytest` - the same toolchain conventions as satay-runtime, since this project
depends on it directly.

## Build status

**Trust the code over the docs.** `docs/` describes the intended system; where
the two disagree, the code is the truth - `ls src/cuttlefish/`, `git log
--oneline`, and a module's own doc comment all beat a paragraph here. Read
[`docs/PLAN.md`](docs/PLAN.md) first for the problem and shape, then
[`docs/adr/`](docs/adr/) for why each load-bearing decision was made, then
[`docs/SLICES.md`](docs/SLICES.md) for the build order this was built against.
`docs/QUESTIONS.md` is the full decision register.

**Slice 1 is complete**: all 8 build-plan steps in `docs/SLICES.md` V1 have
landed and merged, each behind its own PR - `make ci` is green on `main`
(lint, `mypy --strict`, the full unit/integration/e2e suite). Progress is
tracked on the `cuttlefish-agent` Pandan board (epics `V1` and `V2`). What
remains open: a live end-to-end demonstration of a real file edit landing
through the policy gate needs a working model credential, which isn't always
available - everything else about R1/R2/R6 is proven by real, unmocked
automated tests already (KAN-1008 tracks that last piece).

What each module is, in one or two lines - read its own doc comment for why,
not this list:

- **`cuttlefish.episodic`** - the tagged-union event log,
  `.cuttlefish/episodic.db` (SQLite), never a table inside satay's own
  `.satay/`. A redactor strips known secret values at append time; an
  unrecognised event type round-trips verbatim instead of being dropped.
  ADR-0004.
- **`cuttlefish.workflow`** - `run_task`, the `@satay.workflow` core loop:
  one task per LLM call, one for the kopicode delegation. ADR-0001.
- **`cuttlefish.delegate`** - shells out to `kopicode run --print`, parses
  its NDJSON stream into one `DelegationOutcome`, writes and passes the
  declared-allowlist policy file KAN-987 added. ADR-0003, and the "one
  external dependency" section below.
- **`cuttlefish.handover`** - the working-memory handover: a token-budget
  check, one bounded LLM call over the recent episodic window, written back
  as an episodic event. ADR-0004, `docs/QUESTIONS.md` Q15.
- **`cuttlefish.llm`** - the `LlmProvider` seam: `OpenRouterLlmProvider` (the
  default) over OpenRouter's OpenAI-compatible endpoint, `ClaudeLlmProvider`
  for a direct Anthropic credential, a keyless `ReplayLlmProvider` for tests.
  `docs/QUESTIONS.md` Q11.
- **`cuttlefish.cli`** - `cuttlefish run "<task>"` / `cuttlefish show
  <task-id>`. `docs/QUESTIONS.md` Q9.

Toolchain: Python 3.12/3.13, `uv`, `ruff`, `mypy --strict`, `pytest` split
into unit/integration/e2e. `make ci` runs the full local-only suite; CI adds
a job that builds kopicode from source so the delegation's integration tests
run against the real binary, not a mock.

## The one external dependency, and what landed with it

Slice 1's kopicode delegation needed a policy gate that didn't exist in
kopicode's codebase - only its ADR did
([kopicode ADR-0011](https://github.com/leejianrong/kopicode/blob/main/docs/adr/0011-unattended-invocation-policy-gate.md)).
It was filed as **kopicode board card KAN-987**, and it shipped on 2026-08-23
(kopicode PR #109, `internal/permission.AllowlistPolicy` plus a `--policy-file`
flag on `run --print`), before this repository's own scaffold existed. Step 8
of [`docs/SLICES.md`](docs/SLICES.md) V1 is no longer gated on an open external
card.

It shipped with a condition worth knowing before touching the delegation task:
kopicode ADR-0011 decision 4 requires orchestrator-side process/container
containment for *any* policy-gated invocation, and names cuttlefish's own
sandbox as the obligated party, with no carve-out for a single trusted
operator. cuttlefish's own [ADR-0002](docs/adr/0002-sandbox-stays-internal-slice-1-accepts-the-risk.md)
defers the sandbox to V2. Slice 1 proceeds anyway, on the same trust-model
reasoning ADR-0002 already states, and records that exception explicitly in
ADR-0002's consequences rather than leaving the tension unwritten - see that
ADR and [`docs/QUESTIONS.md`](docs/QUESTIONS.md) Q25.

## Workflow conventions

- `main` is PR-only now that there's something worth protecting - the initial
  scaffold was the one thing allowed to land directly. Never push straight to
  `main` after that.
- Branch per slice part: `git switch -c feat/<slice>-<part>` off `origin/main`,
  then open a PR. `make ci` green before merging.
- Commit trailer: `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## Boundaries that must not be crossed

These follow directly from the ADRs. Hold them without re-litigating them here.

- **The core loop is a satay workflow from the first commit that runs a task, not
  an ordinary function made durable later.** ADR-0001.
- **Episodic memory is its own SQLite store, never a table inside satay's own
  `.satay/` database.** ADR-0004.
- **No parallel transcript.** Everything a person or another tool reads back is
  derived from the episodic journal, the same discipline kopicode's own journal
  holds and for the same reason - see ADR-0004's context section for what
  happens when a hand-rolled transcript drifts from reality.
- **The sandbox stays an internal package, not a second product**, until there's
  a real second consumer or a concrete, proven reason to spin it out. ADR-0002.
- **No new protocol between cuttlefish and kopicode.** The delegation wraps
  `kopicode run --print` as it exists. ADR-0003.
- **Secrets are redacted from the episodic journal at write time**, not read
  time - by the time a value is readable, it's already committable.

## Secrets

- **Never read or open `.env`.** It holds the real `OPENROUTER_API_KEY` for
  this repo. Refer to `.env.example` instead when you need to know what
  variables are expected - it's the committed template with no real values.

## Pointers

- [`docs/PLAN.md`](docs/PLAN.md) - problem, scope, requirements, shape
- [`docs/adr/`](docs/adr/) - decisions of record, 0001-0004
- [`docs/SLICES.md`](docs/SLICES.md) - the build order and acceptance criteria
- [`docs/QUESTIONS.md`](docs/QUESTIONS.md) - every decision, who made it, and
  where it landed
- [`README.md`](README.md) - what this is, for a human reading the repo cold
- Pandan board `cuttlefish-agent` (board key `CUT`) - build-plan progress as
  epics/stories; `KAN-1001` through `KAN-1008` are slice 1
