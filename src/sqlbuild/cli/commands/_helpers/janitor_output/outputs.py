"""Janitor command output phases."""

from __future__ import annotations

import sys

from sqlbuild.cli.commands._helpers.janitor_output.output import (
    confirmation_text,
    environment_label,
    write_disabled,
    write_plan,
)
from sqlbuild.cli.commands._helpers.janitor_runtime.models import (
    JanitorInvocation,
    JanitorPlanningResult,
)
from sqlbuild.executor.janitor.models import JanitorExecutionResult, JanitorPlan
from sqlbuild.presentation.classes.cli_style import CliStyle


def write_janitor_disabled(*, invocation: JanitorInvocation) -> None:
    """Write janitor disabled output."""

    write_disabled(stream=sys.stdout, use_color=invocation.use_color)


def write_janitor_plan(
    *, invocation: JanitorInvocation, planning_result: JanitorPlanningResult
) -> None:
    """Write janitor plan preview output."""

    write_plan(plan=planning_result.plan, stream=sys.stdout, use_color=invocation.use_color)


def janitor_plan_has_work(planning_result: JanitorPlanningResult) -> bool:
    """Return whether the janitor plan has any cleanup work."""

    plan: JanitorPlan = planning_result.plan
    return bool(
        plan.candidates
        or plan.checkpoint_candidates
        or plan.detached_virtual_environment_candidates
        or plan.expired_virtual_environment_candidates
        or plan.state_backup_candidates
        or plan.expired_lock_candidates
        or plan.direct_state_prune_candidates
        or plan.virtual_state_prune_candidates
    )


def confirm_janitor_plan(*, planning_result: JanitorPlanningResult) -> bool:
    """Prompt for janitor confirmation."""

    plan: JanitorPlan = planning_result.plan
    expected: str = confirmation_text(plan)
    state_candidate_count: int = (
        len(plan.checkpoint_candidates)
        + len(plan.detached_virtual_environment_candidates)
        + len(plan.expired_virtual_environment_candidates)
        + len(plan.state_backup_candidates)
        + len(plan.expired_lock_candidates)
        + len(plan.virtual_state_prune_candidates)
    )
    prune_count: int = len(plan.direct_state_prune_candidates) + len(
        plan.virtual_state_prune_candidates
    )
    if state_candidate_count or prune_count:
        deletion_count: int = len(plan.candidates) + state_candidate_count + prune_count
        sys.stdout.write(
            f"Janitor will delete {deletion_count} items from {environment_label(plan)}.\n"
        )
    else:
        sys.stdout.write(
            f"Janitor will delete {len(plan.candidates)} objects from {environment_label(plan)}.\n"
        )
    if plan.retention_days == 0:
        sys.stdout.write("Retention: disabled (0 days)\n")
        sys.stdout.write("Age metadata will not be checked.\n")
    else:
        sys.stdout.write(f"Retention: {plan.retention_days} days\n")
    sys.stdout.write(f"\nType `{expected}` to continue: ")
    sys.stdout.flush()
    try:
        response: str = input()
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        return False
    return response == expected


def write_janitor_cancelled() -> None:
    """Write janitor cancellation output."""

    sys.stdout.write("Janitor cancelled.\n")


def write_janitor_completion(
    *, invocation: JanitorInvocation, result: JanitorExecutionResult
) -> None:
    """Write janitor execution summary."""

    style: CliStyle = CliStyle(use_color=invocation.use_color)
    sys.stdout.write(style.success(_deleted_message(result=result)) + "\n")


def _deleted_message(*, result: JanitorExecutionResult) -> str:
    deleted_state_count: int = (
        len(result.deleted_checkpoints)
        + len(result.deleted_detached_virtual_environments)
        + len(result.deleted_expired_virtual_environments)
        + len(result.deleted_state_backups)
        + len(result.deleted_expired_locks)
    )
    pruned_state_count: int = len(result.pruned_direct_state) + len(result.pruned_virtual_state)
    non_checkpoint_state_count: int = deleted_state_count - len(result.deleted_checkpoints)
    if non_checkpoint_state_count or pruned_state_count:
        pruned_state_label: str = (
            "state tables" if result.pruned_virtual_state else "direct state tables"
        )
        return (
            f"Deleted {len(result.deleted)} objects, deleted {deleted_state_count} "
            f"state items, and pruned {pruned_state_count} {pruned_state_label}."
        )
    if result.deleted_checkpoints:
        return (
            f"Deleted {len(result.deleted)} objects and "
            f"{len(result.deleted_checkpoints)} checkpoints."
        )
    return f"Deleted {len(result.deleted)} objects."
