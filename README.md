# cuttlefish-crew

A fleet manager for teams of coding sub-agents, running across many software
projects at once, so the operator stops babysitting a single agent's context
window and its own demos by hand.

Give a project's team a task in plain language. Each agent hands its coding
work to a pluggable backend (today: [kopicode](https://github.com/leejianrong/kopicode),
soon also headless Claude Code) rather than attempting the edit itself. If a
task's process dies partway through, restarting it resumes from where it left
off instead of starting over, because the core loop is a durable
[satay](https://github.com/leejianrong/satay-runtime) workflow from the first
line of code, not an ordinary async function wrapped in durability later.
Everything that happens is written to one readable record, not scattered
across logs that disagree with each other.

## Status

V1 and V2 are both complete and merged: a real `cuttlefish run "<task>"`
delegates to a real kopicode, behind its real declared-allowlist policy gate,
journaled to a real episodic record, optionally routed through a real
sandbox, surviving a real killed-and-resumed process. See
[`CLAUDE.md`](CLAUDE.md)'s build-status section for that history.

As of 2026-09-20, the project is pivoting into **cuttlefish-crew**: a fleet
manager running teams of coding sub-agents across many software projects at
once, dashboard-observable, with automated context handover, steerable chat,
and a hosting story for viewing a real demo without being at the machine
it's running on. [`docs/PLAN.md`](docs/PLAN.md) is the current plan for that
direction; the decisions behind it start at `docs/QUESTIONS.md` Q28, and five
architectural decisions (including this pivot's own) live in
[`docs/adr/`](docs/adr/). The build order is in [`docs/SLICES.md`](docs/SLICES.md).

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
summarised by hand. That's the problem V1/V2 solved, for one agent, one task.

The pain that's actually left, running coding agents for real: babysitting a
single agent's context window, and babysitting its output - the UI, the demo,
the actual user-facing behavior - because a green test suite doesn't tell you
the product is right. Neither goes away with one durable task, and both
compound the moment there's more than one project worth running unattended
at once, with nowhere to see what every project's team is doing without
being at the keyboard for each one. cuttlefish-crew is the fleet-level
answer: a team per project, automated handover instead of manual `/clear`,
and a dashboard the operator can watch from anywhere.

## What it's built on, and why

**satay-runtime, from the first commit, not bolted on later.** sibei-flow (a sibling
project in this suite) already learned this lesson the hard way: its agent loop was
a plain `for` loop over local variables, and a crash at turn 4 of 6 lost everything
and re-billed every model call on restart. Durability retrofitted after the fact is
a rewrite of the part of the system that most needs to be correct. cuttlefish's
core loop is a `@satay.workflow`, and every LLM call and every delegation is a
`@satay.task`, from day one. See [ADR-0001](docs/adr/0001-satay-workflow-as-the-core-loop.md).

**Delegation wraps each backend's own existing headless surface, pluggably.**
`kopicode run --print` already emits newline-delimited JSON on stdout instead
of driving a terminal, built for kopicode's own benchmark runner but
structurally exactly what a supervisor needs - cuttlefish-crew wraps it as a
durable satay task rather than inventing a new protocol between the
processes. That reasoning holds for whichever backend runs a given team's
work, not just kopicode: kopicode is the reference implementation, headless
Claude Code is the second, both behind one `AgentBackend` interface rather
than the project being hardcoded to either. See
[ADR-0003](docs/adr/0003-kopicode-delegation-is-a-wrapped-headless-invocation.md)
(kopicode's own delegation mechanics, still accurate) and
[ADR-0005](docs/adr/0005-agent-backend-becomes-a-pluggable-protocol.md) (why
it's no longer the only one).

**Two sandbox backends exist, and containment stays an internal package.**
V2 built `cuttlefish/sandbox` for real: a container-backed provider (no
account needed) and an E2B-backed one (built, not yet run against a live
account), both behind one create/exec/snapshot/destroy interface, opt-in via
`CUTTLEFISH_SANDBOX`. It stays an internal package rather than becoming a
separate product, because this suite already made the opposite mistake once
with kopicode's own engine and reversed it. See
[ADR-0002](docs/adr/0002-sandbox-stays-internal-slice-1-accepts-the-risk.md),
now also carrying the multi-operator question cuttlefish-crew's product
ambition raises.

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

`cuttlefish-agent` becomes **cuttlefish-crew** as of 2026-09-20, once the
project's direction shifted from a single supervised task to a fleet of
project teams - see [`docs/PLAN.md`](docs/PLAN.md). The Python package import
path (`cuttlefish`) is unchanged; the repository itself is still named
`cuttlefish-agent` until that catches up to match.

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
