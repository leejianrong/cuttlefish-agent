"""A team: several named roles delegating concurrently against one project (ADR-0007).

One satay run, one ``task_id`` — not one child workflow per role (ADR-0007's own
Context explains why: a child's run id isn't known until after it starts, and
``run_task``'s own journaling needs its ``task_id`` from the first line). Every
role's delegation is a concurrent ``satay.gather`` of the same
``delegate_to_agent_backend`` task ``cuttlefish.workflow.run_task`` already uses,
tagged with ``role`` on every event it writes so one shared journal still reads back
as N independent threads of activity, and so ``maybe_handover`` can checkpoint each
role on its own, undisturbed by the others.
"""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict

import satay

from cuttlefish import runtime
from cuttlefish.agents.outcome import DelegationOutcome
from cuttlefish.delegate.policy import DEFAULT_SHELL_ALLOWLIST
from cuttlefish.episodic.events import (
    DelegationCompleted,
    DelegationFailed,
    DelegationRefused,
    DelegationStarted,
    TaskCompleted,
    TaskFailed,
    TaskSubmitted,
)
from cuttlefish.handover import DEFAULT_TOKEN_BUDGET, maybe_handover
from cuttlefish.secrets.store import DEFAULT_PROJECT
from cuttlefish.tasks.delegate import delegate_to_agent_backend
from cuttlefish.tasks.journal import journal


class RoleInput(TypedDict):
    """One team member: a name and its own task text.

    ``allow``/``secret_names`` default to the same "nothing declared" posture a
    plain ``cuttlefish run`` takes (``policy.DEFAULT_SHELL_ALLOWLIST``, no declared
    secrets) — a role that needs its own broader policy declares it explicitly, the
    same discipline every other cuttlefish affordance already holds to.
    """

    name: str
    text: str
    allow: NotRequired[list[list[str]]]
    secret_names: NotRequired[list[str]]


class TeamInput(TypedDict):
    """``run_team``'s input. ``team_id`` is the caller's own satay run id (ADR-0001's
    "task_id is the satay run id" discipline, unchanged — a team is still exactly
    one run, just one whose journal several roles share, ADR-0007)."""

    team_id: str
    root: str
    roles: list[RoleInput]
    project: NotRequired[str]
    token_budget: NotRequired[int]


def _failure_reason(outcome: BaseException) -> str:
    """A journalable reason string for a collected `gather` failure (ADR-0027).

    `delegate_to_agent_backend` raising under `return_exceptions=True` arrives here
    as `satay.TaskFailedError`, which carries the original error's type name and
    message rather than the original exception itself (satay's own collect-mode
    contract) — unwrap it so a role's `DelegationFailed` reads exactly as it would
    have outside a team.
    """
    if isinstance(outcome, satay.TaskFailedError):
        return f"{outcome.error_type}: {outcome.error_message}"
    return str(outcome)


@satay.workflow
async def run_team(team_input: TeamInput) -> dict[str, Any]:
    team_id = team_input["team_id"]
    root = team_input["root"]
    roles = team_input["roles"]
    project = team_input.get("project", DEFAULT_PROJECT)
    token_budget = team_input.get("token_budget", DEFAULT_TOKEN_BUDGET)

    for role in roles:
        await journal(team_id, TaskSubmitted(text=role["text"], role=role["name"]))
        await maybe_handover(team_id, token_budget=token_budget, role=role["name"])

    runtime_ = runtime.current()
    sandbox_provider = runtime_.sandbox_provider
    sandbox_name = sandbox_provider.BACKEND_NAME if sandbox_provider is not None else None
    for role in roles:
        await journal(
            team_id,
            DelegationStarted(
                task_text=role["text"],
                root=root,
                policy_allow=role.get("allow", DEFAULT_SHELL_ALLOWLIST),
                sandbox=sandbox_name,
                backend=runtime_.agent_backend,
                project=project,
                secret_names=role.get("secret_names", []),
                role=role["name"],
            ),
        )

    outcomes = await satay.gather(
        *[
            delegate_to_agent_backend(
                role["text"],
                root,
                allow=role.get("allow", DEFAULT_SHELL_ALLOWLIST),
                project=project,
                secret_names=role.get("secret_names"),
            )
            for role in roles
        ],
        return_exceptions=True,
    )

    role_results: dict[str, dict[str, Any]] = {}
    for role, outcome in zip(roles, outcomes, strict=True):
        role_name = role["name"]
        if isinstance(outcome, BaseException):
            reason = _failure_reason(outcome)
            await journal(team_id, DelegationFailed(reason=reason, role=role_name))
            await journal(team_id, TaskFailed(error=reason, role=role_name))
            role_results[role_name] = {"status": "failed", "error": reason}
        elif isinstance(outcome, DelegationOutcome) and outcome.kind == "completed":
            await journal(
                team_id,
                DelegationCompleted(
                    summary=outcome.summary, edited_paths=outcome.edited_paths, role=role_name
                ),
            )
            await journal(team_id, TaskCompleted(result=outcome.summary, role=role_name))
            role_results[role_name] = {
                "status": "completed",
                "result": outcome.summary,
                "edited_paths": outcome.edited_paths,
            }
        else:
            assert isinstance(outcome, DelegationOutcome)
            reason = outcome.reason or outcome.summary
            if outcome.kind == "refused":
                await journal(team_id, DelegationRefused(reason=reason, role=role_name))
            else:
                await journal(team_id, DelegationFailed(reason=reason, role=role_name))
            await journal(team_id, TaskFailed(error=reason, role=role_name))
            role_results[role_name] = {"status": "failed", "error": reason}
        await maybe_handover(team_id, token_budget=token_budget, role=role_name)

    return {"status": _overall_status(role_results), "roles": role_results}


def _overall_status(role_results: dict[str, dict[str, Any]]) -> str:
    statuses = {result["status"] for result in role_results.values()}
    if statuses == {"completed"}:
        return "completed"
    if statuses == {"failed"}:
        return "failed"
    return "partial"
