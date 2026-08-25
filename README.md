# cuttlefish-agent

A long-running assistant that survives crashes and remembers what it did.

Give it a task in plain language. If the task involves code, it hands the coding
part to [kopicode](https://github.com/leejianrong/kopicode) rather than attempting
the edit itself. If the process dies partway through, restarting it resumes from
where it left off instead of starting over, because the core loop is a durable
[satay](https://github.com/leejianrong/satay-runtime) workflow from the first line
of code, not an ordinary async function wrapped in durability later. Everything
that happens is written to one readable record, not scattered across logs that
disagree with each other.

## Status

Slice 1 is built: a real `cuttlefish run "<task>"` delegates to a real kopicode,
behind its real declared-allowlist policy gate, journaled to a real episodic
record, surviving a real killed-and-resumed process. See
[`CLAUDE.md`](CLAUDE.md)'s build-status section for what's done, what each
module is, and the one piece (a live end-to-end run against a working model
credential) still open. The plan that got it there: [`docs/PLAN.md`](docs/PLAN.md),
four architectural decisions in [`docs/adr/`](docs/adr/), the build order in
[`docs/SLICES.md`](docs/SLICES.md), and the full decision register in
[`docs/QUESTIONS.md`](docs/QUESTIONS.md).

## Usage

```bash
uv sync
uv run cuttlefish run "add a .gitignore entry for build artifacts"
uv run cuttlefish show <task-id>   # printed by `run`, above
```

`run` needs a `kopicode` binary on `PATH` (checked before anything else - a
missing one is a config error, not a mid-task failure) and, for a real
provider, `ANTHROPIC_API_KEY` set. `CUTTLEFISH_LLM_PROVIDER=replay` swaps in a
keyless, deterministic provider for smoke-testing the CLI itself.

## Why this exists

Long-running agent assistants (OpenClaw, Hermes, and their kind) run unattended for
long stretches, and the ones available today handle memory badly. A crash loses
whatever wasn't checkpointed. A long session either runs out of context or gets
summarised by hand. Nothing distills what actually worked into something reusable
next time. The operator ends up babysitting the agent to catch these failures,
which defeats the point of running it unattended at all.

This suite already has a coding specialist built and measured (kopicode) and a
durable-execution runtime built and released (satay-runtime). Nothing supervises
either one over an unattended, long-running task. That's this project.

## What it's built on, and why

**satay-runtime, from the first commit, not bolted on later.** sibei-flow (a sibling
project in this suite) already learned this lesson the hard way: its agent loop was
a plain `for` loop over local variables, and a crash at turn 4 of 6 lost everything
and re-billed every model call on restart. Durability retrofitted after the fact is
a rewrite of the part of the system that most needs to be correct. cuttlefish's
core loop is a `@satay.workflow`, and every LLM call and every delegation is a
`@satay.task`, from day one. See [ADR-0001](docs/adr/0001-satay-workflow-as-the-core-loop.md).

**Delegation wraps kopicode's existing headless surface.** `kopicode run --print`
already emits newline-delimited JSON on stdout instead of driving a terminal, built
for kopicode's own benchmark runner but structurally exactly what a supervisor
needs. cuttlefish wraps it as a durable satay task rather than inventing a new
protocol between the two processes. See
[ADR-0003](docs/adr/0003-kopicode-delegation-is-a-wrapped-headless-invocation.md).

**No sandbox yet, and that's a decision, not an oversight.** General-purpose
ephemeral sandboxing (E2B, Modal, and the rest) is already a mature, consolidating
market, and this project has no reason to compete with it. When containment is
built, it stays an internal package here rather than becoming a separate product,
because this suite already made the opposite mistake once with kopicode's own
engine and reversed it. Slice 1 accepts the same trust model kopicode's own
ADR-0008 accepts: one operator, their own task, their own machine. See
[ADR-0002](docs/adr/0002-sandbox-stays-internal-slice-1-accepts-the-risk.md).

**Memory is four tiers, and this milestone builds two.** Working memory (context
budget and an automatic handover) and episodic memory (a durable, readable record
of what happened) ship first. Procedural memory (distilling what worked into
something reusable) and semantic memory (general facts about the operator's
systems) are named and deferred, not designed yet. See
[ADR-0004](docs/adr/0004-memory-is-four-tiers-the-mvp-builds-two.md).

## Naming

`cuttlefish` was `sotong` until 2026-08-23. Sotong is Singlish slang for "clueless"
as much as it's the word for the animal, which is a bad connotation for an
unattended agent to carry. `cuttlefish-crate`, a possible future sandbox product
under the same name, deliberately doesn't exist yet - see ADR-0002.

## The rest of the suite

- [kopicode](https://github.com/leejianrong/kopicode) - the coding specialist this
  project delegates to.
- [satay-runtime](https://github.com/leejianrong/satay-runtime) - the durable
  runtime this project's core loop is built on.
- [sibei-flow](https://github.com/leejianrong/sibei-flow) - auto-heals broken data
  pipelines; the project whose hand-rolled transcript is the lesson ADR-0004's
  episodic journal design is built to avoid repeating.
- [tingkat](https://github.com/leejianrong/tingkat) - a multi-LoRA routing
  benchmark, unrelated to this project directly but part of the same suite.

## Licence

Apache-2.0, matching every other repository in this suite. See [LICENSE](LICENSE).
