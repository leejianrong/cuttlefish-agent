# ADR-0005: The coding-agent backend is a pluggable protocol, not a wrapped kopicode call

- Status: Accepted
- Date: 2026-09-20
- Deciders: Jian
- Supersedes: the single-backend assumption in [ADR-0003](0003-kopicode-delegation-is-a-wrapped-headless-invocation.md) (that ADR's account of *how* the kopicode wrapping itself works is not superseded - see the note added to it)

## Context

cuttlefish is pivoting into cuttlefish-crew: a fleet manager running teams of
coding sub-agents across many software projects at once, aimed squarely at a
pain the operator actually has running coding agents day to day - babysitting
a single agent's context window, and babysitting its output. That pain is
real today against Claude Code, not against kopicode. A system built to
relieve exactly that pain, while remaining hardcoded to delegate only to a
different tool than the one causing the pain, would not actually solve the
problem it exists to solve.

ADR-0003 reasoned correctly about the call it was making: `kopicode run
--print` was already the right surface to wrap, and inventing a bespoke
wire protocol instead of using it would have been a late, redundant move.
None of that reasoning was wrong. What ADR-0003 also assumed, without
stating it as a separate decision, is that kopicode would be the *only*
thing on the other end of that call. That assumption is what this ADR
revisits, not the wrapping mechanics themselves.

satay-runtime's own ADR-0025 (checked directly against its source,
2026-09-20) already frames satay as a runtime *for agentic applications*,
names a second real agentic consumer's pressure as the trigger that should
promote a hand-rolled pattern into the core, and treats "no loop framework,
no tool-call primitives" as a deliberate non-goal for itself, precisely so
that consumers like cuttlefish-crew define their own agent-facing shape.
Generalizing the delegation surface here is squarely inside what satay's own
roadmap already expects of a second consumer, not a departure from it.

## Decision

**The coding-agent backend is a `cuttlefish.agents.AgentBackend` protocol,
not a kopicode-specific call site.** An `AgentBackend` implementation is
responsible for: invoking its own tool with a task and a target checkout,
parsing whatever native stream or output format that tool produces into one
shared `DelegationOutcome` shape, accepting (or declaring it cannot honor) a
policy file, and reporting what containment/policy guarantees it can
actually make. cuttlefish-crew's own episodic events, sandbox routing, and
policy plumbing are all written against `DelegationOutcome` and the backend
protocol, never against a specific tool's own wire shape.

Two implementations exist as of this ADR:

- **`KopicodeBackend`** - today's delegation logic (ADR-0003's `run --print`
  wrapping, NDJSON parsing, KAN-987-descended policy file generation) moved
  behind the interface with no behavior change. It remains the reference
  implementation and the one with the most mature policy gate.
- **`ClaudeCodeBackend`** - headless Claude Code wrapped the same way,
  proving the interface generalizes past kopicode's own shape rather than
  being accidentally kopicode-shaped.

Selection is a config value, `CUTTLEFISH_AGENT_BACKEND=kopicode|claude-code`,
mirroring the pattern `CUTTLEFISH_SANDBOX` already established for the
sandbox seam (ADR-0002's addenda).

This does not reopen ADR-0003's actual reasoning about the `kopicode run
--print` wrapping mechanism, side-effect marking, or idempotency-key
derivation - those stay exactly as decided, now describing what
`KopicodeBackend` specifically does. What's superseded is only the framing
that this is the *only* backend cuttlefish will ever have.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Keep kopicode as the only backend; it already has the more mature policy gate. | Doesn't solve the pain motivating the whole pivot - Claude Code, not kopicode, is what the operator babysits today. Shipping this pivot's first slice without addressing that would ship the pivot without its own reason to exist. |
| Invent a shared wire protocol every backend must implement, rather than one adapter per backend's own native surface. | Repeats exactly the mistake ADR-0003 already argued against, now applied per-backend: each backend already exposes a serviceable native invocation surface (kopicode's `run --print`, headless Claude Code's own equivalent). The adapter belongs on cuttlefish-crew's side of the boundary, not as a protocol both sides must agree to implement. |
| Wait until a second backend is a proven, forced need before generalizing the interface. | The pain motivating this entire pivot *is* the second backend. Building slice A without it would leave the pivot's first slice not actually addressing the problem that justifies the pivot. |

## Consequences

The system now targets the operator's actual daily pain directly, and the
abstraction is proven against two real, different tools rather than being
speculative. `KopicodeBackend`'s existing behavior is the regression
baseline (R1 in `docs/PLAN.md`) - nothing about today's NDJSON parsing,
policy file generation, or sandbox routing is allowed to change shape while
moving behind the interface.

It also costs real things, named rather than hidden: two invocation surfaces
now need real-binary testing (this project's standing discipline, no mocks),
not one; and backend capability differs in ways that can't be papered over -
kopicode's KAN-987 policy gate is purpose-built and mature, headless Claude
Code's own permission model may not map onto the same declared-allowlist
shape. `docs/PLAN.md`'s R6 (sandbox/policy routing works "per-backend, not
only for kopicode") may not be uniformly satisfiable as a result; the
planned answer is an honest per-backend capability report rather than a
forced uniform contract, but this is unverified until `ClaudeCodeBackend` is
built against a real policy requirement.
