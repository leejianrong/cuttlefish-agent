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
    SteeringMessage,
    TaskCompleted,
    TaskFailed,
    TaskSubmitted,
)
from cuttlefish.handover import DEFAULT_TOKEN_BUDGET, maybe_handover
from cuttlefish.secrets.store import DEFAULT_PROJECT
from cuttlefish.steering import DEFAULT_STEERING_GRACE_SECONDS, compose_steered_text, steering_key
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
    one run, just one whose journal several roles share, ADR-0007).

    ``steerable`` (ADR-0008) is optional and defaults to ``False``, applying to
    every role team-wide — the same "one flag, every role" posture ``--allow``/
    ``--secret`` already take. See ``cuttlefish.workflow.TaskInput`` for what it
    does; here it's a per-role round loop that stays outside this workflow's own
    ``satay.gather`` fan-out rather than nested inside one of its members (ADR-0008's
    own reasoning for why). ``steering_grace`` overrides
    ``steering.DEFAULT_STEERING_GRACE_SECONDS`` team-wide, the same test-only
    escape hatch ``cuttlefish.workflow.TaskInput`` has.
    """

    team_id: str
    root: str
    roles: list[RoleInput]
    project: NotRequired[str]
    token_budget: NotRequired[int]
    steerable: NotRequired[bool]
    steering_grace: NotRequired[float]


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
    steerable = team_input.get("steerable", False)
    steering_grace = team_input.get("steering_grace", DEFAULT_STEERING_GRACE_SECONDS)

    for role in roles:
        await journal(team_id, TaskSubmitted(text=role["text"], role=role["name"]))
        await maybe_handover(team_id, token_budget=token_budget, role=role["name"])

    runtime_ = runtime.current()
    sandbox_provider = runtime_.sandbox_provider
    sandbox_name = sandbox_provider.BACKEND_NAME if sandbox_provider is not None else None

    role_by_name = {role["name"]: role for role in roles}
    current_text: dict[str, str] = {role["name"]: role["text"] for role in roles}
    round_summaries: dict[str, list[str]] = {role["name"]: [] for role in roles}
    final_outcome: dict[str, DelegationOutcome | BaseException] = {}

    # Round-boundary steering (ADR-0008): each round still gathers only plain
    # delegation calls, the exact proven `satay.gather` shape this workflow
    # already had -- the per-role poll for a queued message happens
    # *sequentially*, after that gather resolves, never nested inside one of its
    # members (see ADR-0008 for why nesting `wait_for_event` under `gather` is an
    # unverified composition of satay's own primitives). A non-steerable team
    # runs exactly one round for every role, byte-for-byte as this workflow
    # always has.
    active_names = [role["name"] for role in roles]
    while active_names:
        for name in active_names:
            role = role_by_name[name]
            await journal(
                team_id,
                DelegationStarted(
                    task_text=current_text[name],
                    root=root,
                    policy_allow=role.get("allow", DEFAULT_SHELL_ALLOWLIST),
                    sandbox=sandbox_name,
                    backend=runtime_.agent_backend,
                    project=project,
                    secret_names=role.get("secret_names", []),
                    role=name,
                ),
            )

        outcomes = await satay.gather(
            *[
                delegate_to_agent_backend(
                    current_text[name],
                    root,
                    allow=role_by_name[name].get("allow", DEFAULT_SHELL_ALLOWLIST),
                    project=project,
                    secret_names=role_by_name[name].get("secret_names"),
                )
                for name in active_names
            ],
            return_exceptions=True,
        )

        next_active: list[str] = []
        for name, outcome in zip(active_names, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                # An infra-level failure (ADR-0027's collected `TaskFailedError`) is
                # never steered around, the same boundary `run_task` holds for its
                # own uncollected `DelegationError` (ADR-0008) -- finalize now.
                reason = _failure_reason(outcome)
                await journal(team_id, DelegationFailed(reason=reason, role=name))
                final_outcome[name] = outcome
                continue

            assert isinstance(outcome, DelegationOutcome)
            if outcome.kind == "completed":
                await journal(
                    team_id,
                    DelegationCompleted(
                        summary=outcome.summary, edited_paths=outcome.edited_paths, role=name
                    ),
                )
            elif outcome.kind == "refused":
                await journal(
                    team_id, DelegationRefused(reason=outcome.reason or outcome.summary, role=name)
                )
            else:
                await journal(
                    team_id, DelegationFailed(reason=outcome.reason or outcome.summary, role=name)
                )
            final_outcome[name] = outcome

            if not steerable:
                continue

            steer_event = await satay.wait_for_event(
                SteeringMessage,
                key=steering_key(team_id, name),
                timeout=steering_grace,
            )
            if steer_event is None:
                continue

            await journal(team_id, steer_event)
            summary = (
                outcome.summary
                if outcome.kind == "completed"
                else (outcome.reason or outcome.summary)
            )
            round_summaries[name].append(summary)
            current_text[name] = compose_steered_text(
                role_by_name[name]["text"], round_summaries[name], steer_event.text
            )
            del final_outcome[name]
            next_active.append(name)

        active_names = next_active

    role_results: dict[str, dict[str, Any]] = {}
    for role in roles:
        name = role["name"]
        outcome = final_outcome[name]
        if isinstance(outcome, BaseException):
            reason = _failure_reason(outcome)
            await journal(team_id, TaskFailed(error=reason, role=name))
            role_results[name] = {"status": "failed", "error": reason}
        elif outcome.kind == "completed":
            await journal(team_id, TaskCompleted(result=outcome.summary, role=name))
            role_results[name] = {
                "status": "completed",
                "result": outcome.summary,
                "edited_paths": outcome.edited_paths,
            }
        else:
            reason = outcome.reason or outcome.summary
            await journal(team_id, TaskFailed(error=reason, role=name))
            role_results[name] = {"status": "failed", "error": reason}
        await maybe_handover(team_id, token_budget=token_budget, role=name)

    return {"status": _overall_status(role_results), "roles": role_results}


def _overall_status(role_results: dict[str, dict[str, Any]]) -> str:
    statuses = {result["status"] for result in role_results.values()}
    if statuses == {"completed"}:
        return "completed"
    if statuses == {"failed"}:
        return "failed"
    return "partial"
