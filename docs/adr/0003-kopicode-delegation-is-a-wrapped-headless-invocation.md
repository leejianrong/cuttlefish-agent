# ADR-0003: Delegation to kopicode wraps its existing headless surface, as a durable task

- Status: Accepted
- Date: 2026-08-23
- Deciders: Jian

## Context

cuttlefish needs to hand coding subtasks to a specialist rather than attempting
them itself, and kopicode is that specialist, already built and already measured
against a real benchmark corpus. The question this ADR settles is narrow: how does
one process call the other, given that cuttlefish runs unattended and kopicode's
default posture assumes a human is present to answer a consent prompt.

kopicode already exposes almost exactly the interface a supervisor needs.
`kopicode run --print` runs one prompt and emits newline-delimited JSON events on
stdout instead of driving a terminal - built for kopicode's own benchmark runner,
but structurally identical to what an external caller needs to drive kopicode as a
subordinate worker and read back what happened. There is no reason to invent a
second interface when this one already exists and is exercised by kopicode's own
test suite.

The harder part is consent. kopicode's permission gate is built entirely around a
human answering yes, no, or always at a terminal, and its headless mode
(`run --print`) currently refuses every consent-requiring action unconditionally,
which is the only honest default it can have without a declared policy to answer
instead. kopicode's own ADR-0011, accepted the same day as this one, adds exactly
that: a new, opt-in `permission.Policy` that answers from a declared allowlist
instead of a human, with every decision attributed to the policy rather than a
person. It does not exist in kopicode's codebase yet - it is filed as
kopicode board card KAN-987, for the agent already working in that repository to
build. This project depends on it landing, and does not attempt to build it here;
duplicating kopicode's own permission logic inside cuttlefish would create exactly
the kind of second implementation that drifts from the one kopicode's tests
actually hold to a contract.

Wider industry context matters here too. A bespoke agent-to-agent protocol would be
a late move in 2026: Google's A2A protocol already has real governance (it moved to
the Linux Foundation) and over 150 adopting organisations. That argues against
inventing a wire format for this call and for using what already exists on the
kopicode side instead.

## Decision

**The delegation is a `@satay.task`, marked `side_effect=True`, that shells out to
`kopicode run --print` with the task text, the target repository or scratch
checkout, and the declared policy KAN-987 will add, then parses the NDJSON stream
back into the task's return value.**

`side_effect=True` and a runtime-derived idempotency key are used because this call
genuinely has real-world effects (it edits files, and may run shell commands once
the policy allows it), and satay's own execution guarantees exist precisely to make
a retried side-effecting call safe rather than repeated.

Nothing about kopicode's own interface changes for this. cuttlefish is a consumer
of `run --print` and of the policy gate KAN-987 will add, on exactly the same terms
any other caller would be. No new protocol is defined, and no cross-process
contract exists that kopicode's own maintainers didn't already choose to expose.

## Alternatives considered

| Option | Why not |
|--------|---------|
| A new, bespoke wire protocol between cuttlefish and kopicode. | Redundant with `run --print`, and out of step with where multi-agent interop is actually heading (A2A), which is a real governed standard now, not a greenfield problem to solve again. |
| Import kopicode as a library. | kopicode is Go; cuttlefish is Python. A process boundary with a well-defined wire format is the only sane option, and it's the one that already exists. |
| Reimplement kopicode's permission logic inside cuttlefish, so cuttlefish decides what's allowed rather than kopicode. | Creates a second implementation of a policy that has to match kopicode's own consent semantics exactly, with no shared test suite holding the two in step. kopicode's own policy gate, once KAN-987 lands, is the single place that logic should live. |
| Wait for KAN-987 to land before starting any of cuttlefish's own work. | Unnecessary. Everything else in slice 1 (the workflow shape, the CLI, the episodic journal) doesn't depend on it, and the delegation task itself can be written and tested against kopicode's current, more restrictive headless behaviour, then exercised for real once the policy gate exists. |

## Consequences

cuttlefish's slice 1 has a real, external, cross-repository dependency: it cannot
demonstrate a delegated task that writes a file or runs a command until KAN-987
lands in kopicode. This is named as an open risk in the plan, not hidden inside the
build order. What it can demonstrate before then is the mechanism: the delegation
task itself, its retry and idempotency behaviour, and its handling of kopicode's
current refusal, all of which are real and testable against kopicode's headless
surface as it exists today.

It also means cuttlefish inherits kopicode's own consent posture rather than
inventing a competing one, which is the correct outcome: a single project should
decide what a shell command belonging to its own tool set is allowed to do.
