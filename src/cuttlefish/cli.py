"""cuttlefish's command-line surface (docs/PLAN.md Affordances, QUESTIONS.md Q9).

``cuttlefish run "<task>"`` submits a task and blocks until it reaches a terminal
state, printing a JSON result and exiting with a code from a small fixed set.
``cuttlefish show <task-id>`` renders one task's full episodic record for a person
to read afterward — both derived from exactly the same journal, never a second
transcript (ADR-0004).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

import satay
from dotenv import load_dotenv

from cuttlefish import runtime
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.handover import DEFAULT_TOKEN_BUDGET
from cuttlefish.llm.provider import LlmProvider
from cuttlefish.workflow import run_task

# Loaded once, at import time, not inside main(): main() also runs in-process in
# tests (never via subprocess - see tests/e2e/test_cli.py's own docstring), and
# those rely on monkeypatch.delenv clearing a credential for the duration of one
# test. Reloading .env on every main() call would put it right back.
load_dotenv()

#: Exit codes (QUESTIONS.md Q9: "a small fixed set").
EXIT_OK = 0
EXIT_TASK_FAILED = 1
EXIT_CONFIG_ERROR = 2
EXIT_WORKFLOW_ERROR = 3

KOPICODE_BIN_ENV = "CUTTLEFISH_KOPICODE_BIN"
DEFAULT_KOPICODE_BIN = "kopicode"
LLM_PROVIDER_ENV = "CUTTLEFISH_LLM_PROVIDER"
DEFAULT_LLM_PROVIDER = "openrouter"


class ConfigError(Exception):
    """A startup configuration problem, checked before a task is accepted (Q17)."""


def _resolve_kopicode_binary() -> str:
    return os.environ.get(KOPICODE_BIN_ENV, DEFAULT_KOPICODE_BIN)


def _check_kopicode_on_path(binary: str) -> None:
    """Fail closed, before a task is even accepted (Q17) — not discovered mid-task."""
    if shutil.which(binary) is None:
        raise ConfigError(
            f"kopicode binary {binary!r} is not on PATH. Install kopicode, or set "
            f"{KOPICODE_BIN_ENV} to its path."
        )


def _resolve_llm_provider() -> LlmProvider:
    """cuttlefish's own reasoning provider (QUESTIONS.md Q11).

    "replay" is a test/debug escape hatch, not a documented operator choice: it
    answers every call with a fixed, uninformative response so `cuttlefish run`
    can be smoke-tested with no live credential. A real run defaults to
    "openrouter" — one key over an OpenAI-compatible endpoint reaches many
    upstream models, rather than locking cuttlefish to a single vendor SDK.
    "claude" remains available for a direct Anthropic credential.
    """
    choice = os.environ.get(LLM_PROVIDER_ENV, DEFAULT_LLM_PROVIDER)
    if choice == "openrouter":
        from cuttlefish.llm.openrouter import MissingApiKeyError, OpenRouterLlmProvider

        try:
            return OpenRouterLlmProvider()
        except MissingApiKeyError as exc:
            raise ConfigError(str(exc)) from exc
    if choice == "claude":
        from cuttlefish.llm.claude import ClaudeLlmProvider

        return ClaudeLlmProvider()
    if choice == "replay":
        from cuttlefish.llm.provider import LlmResponse
        from cuttlefish.llm.replay import ReplayLlmProvider

        return ReplayLlmProvider(
            [LlmResponse(model="replay", text="(no real summary — replay provider)")] * 1000
        )
    raise ConfigError(
        f"unknown {LLM_PROVIDER_ENV}={choice!r}; expected 'openrouter', 'claude', or 'replay'"
    )


async def _run(args: argparse.Namespace) -> int:
    kopicode_binary = _resolve_kopicode_binary()
    try:
        _check_kopicode_on_path(kopicode_binary)
        llm_provider = _resolve_llm_provider()
    except ConfigError as exc:
        print(f"cuttlefish: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    episodic_store = EpisodicStore.open(Path.cwd() / ".cuttlefish" / "episodic.db")
    runtime.configure(
        runtime.Runtime(
            episodic_store=episodic_store,
            llm_provider=llm_provider,
            kopicode_binary=kopicode_binary,
        )
    )

    task_id = str(uuid.uuid4())
    root = str(Path(args.root).resolve()) if args.root else str(Path.cwd())

    try:
        async with satay.run_app() as store:
            handle = satay.start(
                run_task,
                {
                    "task_id": task_id,
                    "text": args.task,
                    "root": root,
                    "token_budget": args.token_budget,
                },
                run_id=task_id,
                store=store,
            )
            result = await handle.result()
    except satay.WorkflowFailedError as exc:
        print(json.dumps({"task_id": task_id, "status": "error", "error": str(exc)}))
        return EXIT_WORKFLOW_ERROR
    finally:
        episodic_store.close()

    print(json.dumps({"task_id": task_id, **result}))
    return EXIT_OK if result["status"] == "completed" else EXIT_TASK_FAILED


def _show(args: argparse.Namespace) -> int:
    episodic_store = EpisodicStore.open(Path.cwd() / ".cuttlefish" / "episodic.db")
    try:
        events = list(episodic_store.read(args.task_id))
    finally:
        episodic_store.close()

    if not events:
        print(f"cuttlefish: no events recorded for task {args.task_id!r}", file=sys.stderr)
        return EXIT_TASK_FAILED

    for event in events:
        print(
            f"{event.seq}. {event.ts.isoformat()} {type(event.payload).__name__}: {event.payload}"
        )
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cuttlefish")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Submit a task and block until it finishes")
    run_parser.add_argument("task", help="The task text, in plain language")
    run_parser.add_argument(
        "--root",
        default=None,
        help="The repository or scratch checkout to delegate against (default: CWD)",
    )
    run_parser.add_argument(
        "--token-budget",
        type=int,
        default=DEFAULT_TOKEN_BUDGET,
        help="Working-memory handover threshold, in estimated tokens",
    )

    show_parser = subparsers.add_parser("show", help="Render one task's full episodic record")
    show_parser.add_argument("task_id", help="The task id (the satay run id it was started with)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return asyncio.run(_run(args))
    return _show(args)


if __name__ == "__main__":
    sys.exit(main())
