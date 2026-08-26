"""Process-wide configuration for cuttlefish's satay tasks.

A satay task's arguments and return value are durably journaled (satay's own
``journal.codec``), so a shared resource that isn't itself serialisable data — the
episodic store, the LLM provider, which kopicode binary to shell out to — can't be
passed as a task argument. It's configured once here, before a task's workflow is
started, the same way an application configures a database connection pool once at
process startup rather than threading it through every call.
"""

from __future__ import annotations

from dataclasses import dataclass

from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.llm.provider import LlmProvider
from cuttlefish.sandbox.provider import SandboxProvider


@dataclass(frozen=True, slots=True)
class Runtime:
    """The resources cuttlefish's tasks read when they run.

    ``sandbox_provider`` is ``None`` by default (docs/SLICES.md V2 step 2,
    KAN-1010): a task then runs against a bare scratch checkout exactly as V1
    always did, the named exception ADR-0002's addendum already accepts, not a
    new default this project is quietly widening. Configuring one is opt-in
    (``cuttlefish.cli``'s ``CUTTLEFISH_SANDBOX`` environment variable).
    """

    episodic_store: EpisodicStore
    llm_provider: LlmProvider
    kopicode_binary: str
    sandbox_provider: SandboxProvider | None = None


_runtime: Runtime | None = None


def configure(runtime: Runtime) -> None:
    """Set the process-wide runtime. Call once, before starting any workflow."""
    global _runtime
    _runtime = runtime


def current() -> Runtime:
    """The configured runtime. Raises if `configure` was never called."""
    if _runtime is None:
        raise RuntimeError("cuttlefish.runtime.configure() must be called before running a task")
    return _runtime


def reset() -> None:
    """Clear the configured runtime — test-only, so one test's config can't leak."""
    global _runtime
    _runtime = None
