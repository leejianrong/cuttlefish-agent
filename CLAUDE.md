# CLAUDE.md - agent brief for cuttlefish-agent

cuttlefish is a long-running, unattended task assistant, built on
[satay-runtime](https://github.com/leejianrong/satay-runtime) for durability and
delegating coding subtasks to [kopicode](https://github.com/leejianrong/kopicode)
over its existing headless interface. Python, `uv`, `ruff`, `mypy --strict`,
`pytest` - the same toolchain conventions as satay-runtime, since this project
depends on it directly.

## Nothing is built yet

This repository currently holds a plan, not code. Read
[`docs/PLAN.md`](docs/PLAN.md) first, then [`docs/adr/`](docs/adr/) for why each
load-bearing decision was made, then [`docs/SLICES.md`](docs/SLICES.md) for the
build order. `docs/QUESTIONS.md` is the full decision register, including which
defaults were assumed rather than decided, and what it costs if one turns out to
be wrong.

Once code exists, this section becomes a build-status summary the way kopicode's
own `CLAUDE.md` has one. Keep it lean when that happens: one to three lines per
package, pointing at the package's own doc comment and the relevant ADR for the
reasoning, not a paragraph reproducing it. kopicode's own agent brief grew to
over a thousand lines of exactly that duplication before it was cut back down -
don't repeat that here.

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

- `main` is protected once there's something worth protecting - PR-only, never
  push straight to `main` after the initial scaffold lands.
- Branch per slice: `git switch -c feat/<slice>` off `origin/main`, then open a
  PR.
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

## Pointers

- [`docs/PLAN.md`](docs/PLAN.md) - problem, scope, requirements, shape
- [`docs/adr/`](docs/adr/) - decisions of record, 0001-0004
- [`docs/SLICES.md`](docs/SLICES.md) - the build order and acceptance criteria
- [`docs/QUESTIONS.md`](docs/QUESTIONS.md) - every decision, who made it, and
  where it landed
- [`README.md`](README.md) - what this is, for a human reading the repo cold
