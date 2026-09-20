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
import shlex
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import satay
from dotenv import load_dotenv

from cuttlefish import runtime
from cuttlefish.agents.backend import AgentBackend
from cuttlefish.agents.registry import resolve_backend
from cuttlefish.episodic.redact import DEFAULT_SECRET_ENV_VARS, Redactor
from cuttlefish.episodic.store import EpisodicStore
from cuttlefish.handover import DEFAULT_TOKEN_BUDGET
from cuttlefish.llm.provider import LlmProvider
from cuttlefish.sandbox.provider import SandboxProvider
from cuttlefish.secrets.store import (
    SECRETS_KEY_ENV,
    SHARED_SCOPE,
    InvalidSecretsKeyError,
    MissingSecretsKeyError,
    SecretsStore,
    generate_key,
)
from cuttlefish.team import RoleInput, run_team
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
CLAUDE_CODE_BIN_ENV = "CUTTLEFISH_CLAUDE_CODE_BIN"
DEFAULT_CLAUDE_CODE_BIN = "claude"
AGENT_BACKEND_ENV = "CUTTLEFISH_AGENT_BACKEND"
DEFAULT_AGENT_BACKEND = "kopicode"
LLM_PROVIDER_ENV = "CUTTLEFISH_LLM_PROVIDER"
DEFAULT_LLM_PROVIDER = "openrouter"
SANDBOX_ENV = "CUTTLEFISH_SANDBOX"
DEFAULT_SANDBOX = "none"


class ConfigError(Exception):
    """A startup configuration problem, checked before a task is accepted (Q17)."""


def _resolve_kopicode_binary() -> str:
    return os.environ.get(KOPICODE_BIN_ENV, DEFAULT_KOPICODE_BIN)


def _resolve_claude_code_binary() -> str:
    return os.environ.get(CLAUDE_CODE_BIN_ENV, DEFAULT_CLAUDE_CODE_BIN)


def _resolve_agent_backend() -> str:
    """Which :class:`~cuttlefish.agents.backend.AgentBackend` a delegation runs
    through (ADR-0005, PLAN.md's Affordances) — "kopicode" by default, matching
    V1/V2's only backend.
    """
    choice = os.environ.get(AGENT_BACKEND_ENV, DEFAULT_AGENT_BACKEND)
    if choice not in ("kopicode", "claude-code"):
        raise ConfigError(
            f"unknown {AGENT_BACKEND_ENV}={choice!r}; expected 'kopicode' or 'claude-code'"
        )
    return choice


def _check_binary_on_path(binary: str, *, env_hint: str) -> None:
    """Fail closed, before a task is even accepted (Q17) — not discovered mid-task."""
    if shutil.which(binary) is None:
        raise ConfigError(f"{binary!r} is not on PATH. Install it, or set {env_hint} to its path.")


def _parse_allow(values: list[str] | None) -> list[list[str]]:
    """Each ``--allow`` value is one allowed command, shell-quoted (e.g. ``"go
    test"``), split into the argv list kopicode's own declared-allowlist grammar
    expects (KAN-1011, docs/SLICES.md V2 step 3). No flag at all keeps V1's
    original default: no shell command allowed.
    """
    return [shlex.split(value) for value in values] if values else []


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


def _resolve_sandbox_provider() -> SandboxProvider | None:
    """Real containment for the kopicode delegation (docs/SLICES.md V2 step 2,
    KAN-1010) — opt-in, not the default. "none" (unset) keeps V1's original
    behaviour: the delegation runs directly against ``--root``, the named
    exception ADR-0002's addendum already accepts, not silently widened for
    every operator just because a sandbox package now exists.
    """
    choice = os.environ.get(SANDBOX_ENV, DEFAULT_SANDBOX)
    if choice == "none":
        return None
    if choice == "container":
        from cuttlefish.sandbox.container import ContainerSandboxProvider, DockerNotAvailableError

        try:
            return ContainerSandboxProvider()
        except DockerNotAvailableError as exc:
            raise ConfigError(str(exc)) from exc
    if choice == "e2b":
        from cuttlefish.sandbox.e2b import E2bSandboxProvider, MissingApiKeyError

        try:
            return E2bSandboxProvider()
        except MissingApiKeyError as exc:
            raise ConfigError(str(exc)) from exc
    raise ConfigError(f"unknown {SANDBOX_ENV}={choice!r}; expected 'none', 'container', or 'e2b'")


def _secrets_db_path() -> Path:
    return Path.cwd() / ".cuttlefish" / "secrets.db"


def _resolve_secrets_store() -> SecretsStore | None:
    """Project-scoped secrets (ADR-0006) — opt-in, mirroring
    ``_resolve_sandbox_provider``'s "none by default" posture. An operator who
    never sets ``CUTTLEFISH_SECRETS_KEY`` gets today's exact V1/V2 behaviour:
    no store, every credential still resolved from ``os.environ`` by each
    backend's own ``_credential_envs``.
    """
    if SECRETS_KEY_ENV not in os.environ:
        return None
    try:
        return SecretsStore.open(_secrets_db_path())
    except InvalidSecretsKeyError as exc:
        raise ConfigError(str(exc)) from exc


def _resolve_project_secrets(
    *,
    backend: AgentBackend,
    secrets_store: SecretsStore | None,
    project: str,
    secret_names: list[str],
) -> dict[str, str]:
    """Every name this delegation should try to resolve from `secrets_store` --
    `secret_names` (an operator's own `--secret` declarations) plus whatever
    `backend` always tries ambiently (`AgentBackend.CREDENTIAL_ENV_VARS`,
    ADR-0006) -- resolved eagerly here (not just inside the task) so a missing
    *declared* name fails closed before a task is even accepted (Q17), and so
    the same resolved values can seed the episodic journal's redactor below.
    """
    if secrets_store is None:
        if secret_names:
            raise ConfigError(f"--secret was given but {SECRETS_KEY_ENV} is not set")
        return {}
    names = sorted(set(secret_names) | set(backend.CREDENTIAL_ENV_VARS))
    resolved = secrets_store.resolve(project, names)
    missing = [name for name in secret_names if name not in resolved]
    if missing:
        raise ConfigError(
            f"declared secret(s) not found for project {project!r} or the shared scope: "
            + ", ".join(missing)
        )
    return resolved


@dataclass(frozen=True, slots=True)
class _PreparedRun:
    """Every config seam `run` and `run-team` both resolve identically before
    starting their own workflow — factored out once both needed it (ADR-0007)."""

    kopicode_binary: str
    claude_code_binary: str
    agent_backend: str
    llm_provider: LlmProvider
    sandbox_provider: SandboxProvider | None
    secrets_store: SecretsStore | None
    episodic_store: EpisodicStore

    def close(self) -> None:
        self.episodic_store.close()
        if self.secrets_store is not None:
            self.secrets_store.close()

    def as_runtime(self) -> runtime.Runtime:
        return runtime.Runtime(
            episodic_store=self.episodic_store,
            llm_provider=self.llm_provider,
            kopicode_binary=self.kopicode_binary,
            claude_code_binary=self.claude_code_binary,
            agent_backend=self.agent_backend,
            sandbox_provider=self.sandbox_provider,
            secrets_store=self.secrets_store,
        )


def _prepare_run(*, project: str, secret_names: list[str]) -> _PreparedRun:
    """Resolve the backend, LLM provider, sandbox, secrets store, and a
    secrets-aware redactor — or raise `ConfigError`, closing any secrets store
    already opened first, so a caller only has to print the error and return
    `EXIT_CONFIG_ERROR`, no further cleanup required.
    """
    kopicode_binary = _resolve_kopicode_binary()
    claude_code_binary = _resolve_claude_code_binary()

    secrets_store = None
    try:
        agent_backend = _resolve_agent_backend()
        if agent_backend == "kopicode":
            _check_binary_on_path(kopicode_binary, env_hint=KOPICODE_BIN_ENV)
        else:
            _check_binary_on_path(claude_code_binary, env_hint=CLAUDE_CODE_BIN_ENV)
        backend = resolve_backend(
            agent_backend, kopicode_binary=kopicode_binary, claude_code_binary=claude_code_binary
        )
        llm_provider = _resolve_llm_provider()
        sandbox_provider = _resolve_sandbox_provider()
        secrets_store = _resolve_secrets_store()
        resolved_secrets = _resolve_project_secrets(
            backend=backend,
            secrets_store=secrets_store,
            project=project,
            secret_names=secret_names,
        )
    except ConfigError:
        if secrets_store is not None:
            secrets_store.close()
        raise

    # A store-resolved secret never touches os.environ (ADR-0006), so the
    # redactor's own default (env-only) lookup would silently miss it -- fall
    # back to os.environ only for a name resolved_secrets doesn't have.
    def _redaction_lookup(name: str) -> str | None:
        return resolved_secrets.get(name) or os.environ.get(name)

    redaction_names = sorted(set(DEFAULT_SECRET_ENV_VARS) | set(backend.CREDENTIAL_ENV_VARS))
    episodic_store = EpisodicStore.open(
        Path.cwd() / ".cuttlefish" / "episodic.db",
        redactor=Redactor(redaction_names, lookup=_redaction_lookup),
    )
    return _PreparedRun(
        kopicode_binary=kopicode_binary,
        claude_code_binary=claude_code_binary,
        agent_backend=agent_backend,
        llm_provider=llm_provider,
        sandbox_provider=sandbox_provider,
        secrets_store=secrets_store,
        episodic_store=episodic_store,
    )


def _resolve_root_and_project(args: argparse.Namespace) -> tuple[str, str]:
    root = str(Path(args.root).resolve()) if args.root else str(Path.cwd())
    project = args.project if args.project else Path(root).name
    return root, project


async def _run(args: argparse.Namespace) -> int:
    root, project = _resolve_root_and_project(args)
    secret_names = sorted(set(args.secret or []))

    try:
        prepared = _prepare_run(project=project, secret_names=secret_names)
    except ConfigError as exc:
        print(f"cuttlefish: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    runtime.configure(prepared.as_runtime())
    task_id = str(uuid.uuid4())

    try:
        async with satay.run_app() as store:
            handle = satay.start(
                run_task,
                {
                    "task_id": task_id,
                    "text": args.task,
                    "root": root,
                    "token_budget": args.token_budget,
                    "allow": _parse_allow(args.allow),
                    "project": project,
                    "secret_names": secret_names,
                },
                run_id=task_id,
                store=store,
            )
            result = await handle.result()
    except satay.WorkflowFailedError as exc:
        print(json.dumps({"task_id": task_id, "status": "error", "error": str(exc)}))
        return EXIT_WORKFLOW_ERROR
    finally:
        prepared.close()

    print(json.dumps({"task_id": task_id, **result}))
    return EXIT_OK if result["status"] == "completed" else EXIT_TASK_FAILED


def _parse_roles(values: list[str] | None) -> list[RoleInput]:
    """Each ``--role`` value is ``NAME:TASK_TEXT``, split on the first ``:`` (ADR-0007).
    Requires at least one; a name declared twice is a config error, not a silent
    overwrite of the first role's own task text.
    """
    if not values:
        raise ConfigError("run-team needs at least one --role NAME:TASK_TEXT")
    roles: list[RoleInput] = []
    seen: set[str] = set()
    for value in values:
        name, sep, text = value.partition(":")
        name, text = name.strip(), text.strip()
        if not sep or not name or not text:
            raise ConfigError(f"--role {value!r} must be NAME:TASK_TEXT")
        if name in seen:
            raise ConfigError(f"--role name {name!r} was declared more than once")
        seen.add(name)
        roles.append({"name": name, "text": text})
    return roles


async def _run_team(args: argparse.Namespace) -> int:
    root, project = _resolve_root_and_project(args)
    secret_names = sorted(set(args.secret or []))

    try:
        roles = _parse_roles(args.role)
        prepared = _prepare_run(project=project, secret_names=secret_names)
    except ConfigError as exc:
        print(f"cuttlefish: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    runtime.configure(prepared.as_runtime())
    team_id = str(uuid.uuid4())
    allow = _parse_allow(args.allow)
    role_inputs: list[RoleInput] = [
        {"name": role["name"], "text": role["text"], "allow": allow, "secret_names": secret_names}
        for role in roles
    ]

    try:
        async with satay.run_app() as store:
            handle = satay.start(
                run_team,
                {
                    "team_id": team_id,
                    "root": root,
                    "project": project,
                    "roles": role_inputs,
                    "token_budget": args.token_budget,
                },
                run_id=team_id,
                store=store,
            )
            result = await handle.result()
    except satay.WorkflowFailedError as exc:
        print(json.dumps({"team_id": team_id, "status": "error", "error": str(exc)}))
        return EXIT_WORKFLOW_ERROR
    finally:
        prepared.close()

    print(json.dumps({"team_id": team_id, **result}))
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


def _open_secrets_store_or_exit() -> SecretsStore:
    try:
        return SecretsStore.open(_secrets_db_path())
    except (MissingSecretsKeyError, InvalidSecretsKeyError) as exc:
        print(f"cuttlefish: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_ERROR) from exc


def _read_secret_value(name: str) -> str:
    """A secret's value, kept off the command line and out of shell history —
    prompted (hidden) on a real terminal, or read as one line from stdin when
    piped (e.g. ``echo "$TOKEN" | cuttlefish secrets set --project foo NAME``).
    """
    if sys.stdin.isatty():
        import getpass

        return getpass.getpass(f"Value for {name}: ")
    return sys.stdin.readline().rstrip("\n")


def _secrets(args: argparse.Namespace) -> int:
    if args.secrets_command == "generate-key":
        print(generate_key())
        return EXIT_OK

    store = _open_secrets_store_or_exit()
    scope = SHARED_SCOPE if args.shared else args.project
    try:
        if args.secrets_command == "set":
            store.set(scope, args.name, _read_secret_value(args.name))
            print(f"cuttlefish: set {args.name!r} for scope {scope!r}")
            return EXIT_OK
        if args.secrets_command == "get":
            value = store.get(scope, args.name)
            if value is None:
                print(f"cuttlefish: no secret {args.name!r} in scope {scope!r}", file=sys.stderr)
                return EXIT_TASK_FAILED
            print(value)
            return EXIT_OK
        if args.secrets_command == "delete":
            if not store.delete(scope, args.name):
                print(f"cuttlefish: no secret {args.name!r} in scope {scope!r}", file=sys.stderr)
                return EXIT_TASK_FAILED
            print(f"cuttlefish: deleted {args.name!r} from scope {scope!r}")
            return EXIT_OK
        # args.secrets_command == "list"
        for name in store.list_names(scope):
            print(name)
        return EXIT_OK
    finally:
        store.close()


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
    run_parser.add_argument(
        "--allow",
        action="append",
        metavar="CMD",
        help=(
            "One shell command the delegation may run inside --root, shell-quoted "
            "(e.g. --allow 'go test'). Repeatable. Default: no shell command allowed."
        ),
    )
    run_parser.add_argument(
        "--project",
        default=None,
        help=(
            "This task's secrets scope (ADR-0006). Default: --root's own directory "
            "name. Only matters if CUTTLEFISH_SECRETS_KEY is set."
        ),
    )
    run_parser.add_argument(
        "--secret",
        action="append",
        metavar="NAME",
        help=(
            "One named secret (beyond a backend's own ambient credential names) "
            "this task's backend may read from --project's scope or the shared "
            "scope. Repeatable. Requires CUTTLEFISH_SECRETS_KEY to be set."
        ),
    )

    run_team_parser = subparsers.add_parser(
        "run-team", help="Run several named roles concurrently against one project (ADR-0007)"
    )
    run_team_parser.add_argument(
        "--role",
        action="append",
        metavar="NAME:TASK_TEXT",
        help=(
            "One role: a name and its own task text, separated by the first ':' "
            "(e.g. --role builder:'implement the login form'). Repeatable; at "
            "least one is required."
        ),
    )
    run_team_parser.add_argument(
        "--root",
        default=None,
        help="The repository or scratch checkout every role delegates against (default: CWD)",
    )
    run_team_parser.add_argument(
        "--token-budget",
        type=int,
        default=DEFAULT_TOKEN_BUDGET,
        help="Working-memory handover threshold per role, in estimated tokens",
    )
    run_team_parser.add_argument(
        "--allow",
        action="append",
        metavar="CMD",
        help=(
            "One shell command every role may run inside --root. Repeatable. Applies to all roles."
        ),
    )
    run_team_parser.add_argument(
        "--project",
        default=None,
        help="Every role's shared secrets scope (ADR-0006). Default: --root's own directory name.",
    )
    run_team_parser.add_argument(
        "--secret",
        action="append",
        metavar="NAME",
        help="One named secret every role may read (ADR-0006). Repeatable. Applies to all roles.",
    )

    show_parser = subparsers.add_parser("show", help="Render one task's full episodic record")
    show_parser.add_argument("task_id", help="The task id (the satay run id it was started with)")

    secrets_parser = subparsers.add_parser(
        "secrets", help="Manage the project-scoped secrets store"
    )
    secrets_sub = secrets_parser.add_subparsers(dest="secrets_command", required=True)
    secrets_sub.add_parser("generate-key", help="Print a fresh CUTTLEFISH_SECRETS_KEY")

    def _add_scope_and_name(p: argparse.ArgumentParser) -> None:
        scope = p.add_mutually_exclusive_group(required=True)
        scope.add_argument("--project", help="The project scope")
        scope.add_argument("--shared", action="store_true", help="The shared scope")
        p.add_argument("name", help="The secret's name, e.g. HUGGINGFACE_TOKEN")

    _add_scope_and_name(
        secrets_sub.add_parser("set", help="Set a secret's value (prompted, or read from stdin)")
    )
    _add_scope_and_name(secrets_sub.add_parser("get", help="Print a secret's value"))
    _add_scope_and_name(secrets_sub.add_parser("delete", help="Delete a secret"))

    list_parser = secrets_sub.add_parser("list", help="List a scope's secret names (never values)")
    list_scope = list_parser.add_mutually_exclusive_group(required=True)
    list_scope.add_argument("--project", help="The project scope")
    list_scope.add_argument("--shared", action="store_true", help="The shared scope")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return asyncio.run(_run(args))
    if args.command == "run-team":
        return asyncio.run(_run_team(args))
    if args.command == "secrets":
        return _secrets(args)
    return _show(args)


if __name__ == "__main__":
    sys.exit(main())
