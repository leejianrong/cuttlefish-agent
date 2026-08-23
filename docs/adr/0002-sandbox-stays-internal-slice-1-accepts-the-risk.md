# ADR-0002: The sandbox stays an internal package, and slice 1 accepts kopicode's own risk posture

- Status: Accepted
- Date: 2026-08-23
- Deciders: Jian

## Context

cuttlefish's whole reason to exist is running tasks with nobody watching, which
means the coding subtasks it delegates to kopicode need to run somewhere a
misbehaving or malicious task can't do real damage. Two separate questions get
tangled together if they aren't pulled apart: whether cuttlefish should ever build
its own sandbox, and whether it needs one on day one.

On the first question, market research done earlier in this suite's planning
found that general-purpose ephemeral-sandbox execution is already a mature,
consolidating market. E2B alone is used by a majority of Fortune 100 companies
doing agentic work, and OpenAI's own Agents SDK shipped a standardised client
covering seven sandbox providers (Blaxel, Cloudflare, Daytona, E2B, Modal, Runloop,
Vercel) as a native integration. Building a competing general-purpose sandbox
product now means competing with funded incumbents already integrated into the
platforms this project's own users are likely to already be using. That argues for
using one of them, not building one.

It also argues against turning cuttlefish's own sandbox wrapper into a second
product. This suite has already made that exact mistake once, with kopicode:
`kopi-engine` was split into its own repository in anticipation of a second
consumer (this project, at the time still called sotong) that didn't exist yet,
and kopicode's own ADR-0003 records folding it back in, in almost these words:
"doing it now is not recoverable effort, it is effort spent on a guess about which
seams matter." A sandbox package spun out before it has a second real consumer, or
before cuttlefish has enough usage to know which parts of the interface actually
need to be stable, repeats that mistake one level up the stack.

On the second question, whether slice 1 needs a sandbox at all: kopicode's own
ADR-0008 already worked through this exact trade-off, for its own shell tool. It
found that a real container or namespace boundary costs a multi-platform
security-engineering effort disproportionate to the audience being served right
now, and that policy scoping alone is real UX hardening for a cooperative model but
not a security boundary against an adversarial one. It accepted the risk
explicitly, named the trust model that makes the risk acceptable (one operator,
their own machine), and wrote down two trigger conditions for revisiting: acquiring
multi-user exposure, or being pointed at untrusted task input.

Nothing about cuttlefish's slice 1 crosses either trigger. It is one operator,
running their own tasks, against their own repositories.

## Decision

**The sandbox is an internal package inside this repository (`cuttlefish/sandbox`),
not a separate product, and slice 1 does not build it at all.**

The package, when it is built, exposes a small provider interface - create, exec,
snapshot, destroy - loosely matching the shape OpenAI's Agents SDK already
standardised, so this project is compatible with an emerging convention rather than
inventing its own. E2B is the only backend when that happens.

Slice 1's kopicode delegation runs against a throwaway scratch checkout instead,
with the same accepted-risk trust model kopicode's own ADR-0008 states: one
operator, running their own task, against a repository or scratch directory they
already trust. This is named explicitly, the same way kopicode named it, rather
than left as an implicit assumption nobody wrote down. Real containment is a slice
2 concern, gated on the identical trigger conditions: cuttlefish acquiring
multi-tenant exposure, or being pointed at task input the operator didn't
author themselves.

If a genuinely differentiated capability shows up later - specifically, a sandbox
snapshot tied to a satay journal turn, so forking a run also forks the sandbox's
filesystem state consistently - that is worth a fresh ADR of its own once there is
real fork-and-replay usage to build it against. It is not decided here, and it is
not what justifies keeping the sandbox internal today.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Build the sandbox as its own product now (cuttlefish-crate). | Repeats kopi-engine's mistake at a different layer, before there's a second consumer or evidence about which parts of the interface need to be stable. |
| Build real E2B containment in slice 1. | Adds an E2B account, an API key, and real operating cost to the riskiest, least-proven slice of a brand-new project, for a risk kopicode's own ADR-0008 already argues doesn't apply yet at this trust level. |
| Skip a sandbox interface entirely and call kopicode directly with no abstraction. | Leaves nothing to swap in when slice 2 actually needs containment, meaning that work starts from zero instead of from a defined seam. |

## Consequences

Slice 1 ships without a security boundary around the kopicode delegation, and this
is a real, named risk, not an oversight - anyone running cuttlefish against a task
they don't fully trust, or on a machine they can't afford to have touched, is
outside what this version was built for. That mirrors kopicode's own posture
exactly, and for the same underlying reason: the audience being served right now
doesn't need the cost paid yet.

It also means slice 2 has real, well-scoped work waiting: the sandbox package,
gated by a trigger condition already written down instead of discovered under
pressure. And it keeps this suite's naming and repository count honest - there is
no cuttlefish-crate until there is a reason for one.

## Addendum, 2026-08-23: kopicode ADR-0011 names this gap explicitly

kopicode board card KAN-987 landed the same day as this ADR
([kopicode ADR-0011](https://github.com/leejianrong/kopicode/blob/main/docs/adr/0011-unattended-invocation-policy-gate.md),
kopicode PR #109), adding the declared-allowlist policy gate slice 1's
delegation task depends on (ADR-0003, `docs/SLICES.md` V1 step 8). Its decision
4 states the requirement without the carve-out this ADR relies on: "real
process or container containment is required for **any** unattended,
policy-gated invocation, and it is the invoking orchestrator's responsibility,"
and names cuttlefish's own sandbox package as the obligated party - not
"unless the operator is a single trusted individual running their own task,"
the exact exception this ADR's own trust model rests on.

This is a real, named tension between the two projects' ADRs, not an oversight
in either: kopicode ADR-0011 is stated generally because kopicode has no way to
know, from inside its own process, whether a given caller is the single-operator
case this ADR describes or a multi-tenant one. cuttlefish does know, because it
is the orchestrator authoring the task and the allowlist in the first place.

Slice 1 proceeds without a sandbox anyway, deliberately, on this ADR's existing
reasoning: the same accepted-risk trust model kopicode's own ADR-0008 states
(one operator, running their own task, against a repository or scratch
directory they already trust) covers a policy-gated real edit exactly as well
as it covers the read-only case that trust model was originally written to
justify. Nothing about the *kind* of action (a bounded shell command or a
confined write, rather than an unconditional refusal) changes who is running
it or what they're running it against. What changes is that the gap is no
longer hypothetical: after KAN-987, slice 1's delegation can cause a real
shell command or file write to happen unattended, and previously it could not
have, since `denyHeadless` refused everything. This addendum exists so that
fact is written down rather than discovered later as a surprise.

This is a deliberate, scoped exception, not a reason to revisit this ADR's
decision. The sandbox still stays out of slice 1. It sharpens slice 2's
trigger condition, though: V2's sandbox is no longer only "if cuttlefish
acquires multi-tenant exposure or untrusted task input" - it is also the thing
that brings cuttlefish's delegation into compliance with kopicode's own stated
contract for using its policy gate at all. See `docs/QUESTIONS.md` Q25.
