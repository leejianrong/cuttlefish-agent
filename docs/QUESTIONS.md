# Questions

Statuses: `DECIDED` (user answered) - `ASSUMED` (default taken, correct it if
wrong) - `FORK` (waiting on the user) - `DEFERRED` (not needed this milestone).

## Open forks

None. Both forks raised in round 1 were resolved the same round.

## Register

| ID | Question | Status | Answer or default | Landed |
|----|----------|--------|--------------------|--------|
| Q1 | Who is the primary user, and who else acts on the system? | DECIDED | The operator who runs cuttlefish is primary. External tools and other agents can submit tasks too, but they act inside whatever the operator has configured - the operator's trust boundary always wins. | PLAN §Users |
| Q2 | What is in the MVP? | DECIDED | One CLI trigger surface, a satay-workflow core loop from day one, episodic memory only, one delegation path to kopicode gated by a hardcoded allowlist, no multi-agent swarm beyond that one delegation. | PLAN §Scope |
| Q3 | What is explicitly out of the MVP? | DECIDED | Chat/webhook trigger surfaces, procedural and semantic memory, the general policy gate, real sandbox containment, any second delegation target, cuttlefish-crate as a separate product. | PLAN §Scope |
| Q4 | kopicode's ADR-0011 policy gate doesn't exist in code - how does slice 1 get it? | FORK -> DECIDED | Filed as kopicode board card KAN-987, for the agent already working in that repo to pick up. Not built inside this repo. | PLAN §Open risks, SLICES.md V1 |
| Q5 | Does slice 1 wire up real E2B containment around the delegation? | FORK -> DECIDED | No. Slice 1 runs against a throwaway scratch checkout with no adversarial-input assumption, the same accepted-risk posture kopicode's own ADR-0008 takes. Real containment is slice 2, gated on the identical trigger kopicode uses. | ADR-0002 |
| Q6 | How is a task addressed - its own ID, or something borrowed? | ASSUMED | A task's ID is the satay run ID that its workflow gets when started. No second identity scheme. | ADR-0001 |
| Q7 | Where does episodic memory actually live? | ASSUMED | Its own SQLite file (`.cuttlefish/episodic.db`), never inside satay's own `.satay/` store. satay owns its schema and its migrations; a second writer into that file would be an unversioned change to a schema this project doesn't own. | ADR-0004 |
| Q8 | Can two tasks run at once in the MVP? | ASSUMED | No. satay-runtime is one process, one writer, with no multi-worker execution yet (checked against its own CLAUDE.md), so sequential processing isn't a choice this project is making, it's a constraint it inherits. A second submission queues. | PLAN §Shape |
| Q9 | What does the CLI actually look like? | ASSUMED | `cuttlefish run "<task text>"` submits and blocks until the workflow reaches a terminal state, then prints a JSON result and exits with a code from a small fixed set. A daemon mode that accepts tasks without blocking is deferred. | PLAN §Affordances |
| Q10 | How does cuttlefish actually hand a task to kopicode? | DECIDED | `kopicode run --print` (kopicode's existing headless, newline-delimited-JSON surface) wrapped as a `side_effect=True` satay task. No new protocol. | ADR-0003 |
| Q11 | What answers cuttlefish's own LLM calls (not kopicode's)? | ASSUMED | An `LlmProvider` seam, the same shape sibei-flow already uses: a keyless deterministic `replay` provider for tests, `claude` or an OpenAI-compatible endpoint for real use, selected by an environment variable. | PLAN §Shape |
| Q12 | What does the sandbox provider abstraction look like, even though it isn't built until v2? | DECIDED | create / exec / snapshot / destroy, loosely matching the shape OpenAI's Agents SDK already standardised across seven sandbox providers, so this project is compatible with an emerging convention rather than inventing one. E2B is the only backend when it's built. | ADR-0002 |
| Q13 | Does the sandbox become its own product (cuttlefish-crate) now? | DECIDED | No. It stays an internal package inside this repo until a second real consumer exists or a genuinely differentiated capability (journal-aware sandbox snapshotting tied to a satay fork) is concrete enough to build. Spinning it out now repeats a mistake this suite already made once and reversed (kopicode's own ADR-0003). | ADR-0002 |
| Q14 | Which memory tiers are in the MVP? | DECIDED | Working memory (context budget and handover) and episodic memory (the durable log). Procedural memory (skill distillation) and semantic memory are both deferred past the MVP. | ADR-0004 |
| Q15 | How does a context handover actually get written? | DECIDED | Never a hand-maintained document. At a token-budget threshold, checkpoint the task via satay's own primitives, run one bounded LLM call over the recent journal window to distill a summary, discard the raw window, and keep a pointer back into the full journal for anything that needs it later. | ADR-0004 |
| Q16 | What happens when a kopicode delegation fails? | ASSUMED | Caught, journaled as a typed episodic event, and surfaced to the caller as a real failure. Not silently retried. | PLAN §Implementation decisions |
| Q17 | What happens if the kopicode binary isn't on PATH? | ASSUMED | A startup configuration error, checked before a task is even accepted, not a per-task failure discovered mid-run. | PLAN §Implementation decisions |
| Q18 | Does cuttlefish ask the operator a clarifying question when a task is ambiguous? | ASSUMED | Not in v1. The CLI is blocking and the operator is present, so this would be buildable, but it is genuinely extra scope past what the MVP needs to prove. Deferred. | PLAN §Scope |
| Q19 | Which satay-runtime version, and is the licence and offline story checked? | DECIDED | `satay` 0.1.0 on PyPI (confirmed live, 2026-08-23), Apache-2.0, runs fully offline over local SQLite. Pinned, not floated. | PLAN §Requirements |
| Q20 | What platforms and Python versions? | ASSUMED | Linux and macOS first-class, Windows best-effort, matching satay-runtime's own posture exactly, since this project can't be more portable than the runtime it sits on. Python 3.12 or 3.13. | PLAN §Requirements |
| Q21 | How would a person or a test know slice 1 actually works? | DECIDED | Four checkable claims: it runs a real task to a terminal state unattended, it survives a killed process and resumes without double-running the kopicode delegation, it delegates at least one real coding subtask to kopicode successfully, and it produces a journal a human can read afterward with no parallel hand-rolled transcript. | SLICES.md V1 |
| Q22 | Who holds the LLM and kopicode-related credentials, and where do they live? | ASSUMED | Environment variables only, never committed, never logged - the same posture as every sibling repo. cuttlefish's own episodic journal needs its own write-time redaction pass; satay's ADR-0029 redaction only covers satay's own journal schema; it does nothing for a second, cuttlefish-owned journal file. | ADR-0004 |
| Q23 | What is cuttlefish's actual trust model, given it's meant to hold credentials and run unattended? | ASSUMED | One trusted operator, same as kopicode's own ADR-0008, but the risk it accepts is different in kind: kopicode's worst case is a bad diff, reversible with `git revert`; cuttlefish's worst case is a long-lived credential misused with nobody watching. Named plainly rather than inherited by assumption. | ADR-0002 |
| Q24 | Are episodic events versioned from the first commit? | ASSUMED | Yes, the same discipline kopicode's own journal uses: an unmarshaller that preserves an unknown future event type rather than dropping it. | ADR-0004 |
| Q25 | kopicode board KAN-987 landed (2026-08-23, PR #109) with ADR-0011 decision 4 requiring orchestrator-side containment for any policy-gated invocation, naming cuttlefish's sandbox as the obligated party, no single-operator carve-out. Does slice 1 still use the policy gate for a real edit without the sandbox? | DECIDED | Yes. Slice 1 proceeds on ADR-0002's existing trust-model reasoning (one operator, their own task, their own checkout) - the same reasoning already accepted for the whole delegation, now extended explicitly to cover a policy-gated real edit rather than only the read-only/refusal case. Written down as a named exception, not silently resolved either way. | ADR-0002 addendum |

## Coverage

| Category | Covered by |
|----------|-----------|
| Primary user and actors | Q1 |
| Scope boundary | Q2, Q3, Q18 |
| Data model and identity | Q6, Q24 |
| State and storage | Q7 |
| Concurrency and conflict | Q8 |
| Interfaces and contracts | Q9, Q10, Q12 |
| Failure behaviour | Q16, Q17 |
| External dependencies | Q4, Q11, Q19 |
| Runtime and deployment | Q20 |
| Measurable success | Q21 |
| Security and secrets | Q22, Q23, Q25 |
| Versioning and migration | Q24 |
