"""Janitor command output helpers."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorExpiredLockCandidate,
    JanitorExpiredVirtualEnvironmentCandidate,
    JanitorPlan,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
    JanitorStateBackupCandidate,
)
from sqlbuild.shared.helpers.colors import blue, blue_bold, dim, green, green_bold, yellow


def write_disabled(*, stream: TextIO, use_color: bool = False) -> None:
    """Write disabled janitor guidance."""

    stream.write(
        f"{_title('Janitor is disabled for this project.', use_color=use_color)}\n\n"
        "Enable it with:\n\n"
        "janitor:\n"
        "  enabled: true\n"
        "  retention_days: 30\n"
    )


def write_plan(*, plan: JanitorPlan, stream: TextIO, use_color: bool = False) -> None:
    """Write a janitor preview."""

    env_label: str = environment_label(plan)
    rendered_env: str = blue_bold(env_label) if use_color else env_label
    stream.write(f"{_title('Janitor preview', use_color=use_color)}  {rendered_env}\n\n")
    if plan.retention_days == 0:
        stream.write(f"  {'retention':<22} {_value('disabled (0 days)', use_color=use_color)}\n")
        stream.write(f"  {'age metadata':<22} {_value('not checked', use_color=use_color)}\n")
    else:
        stream.write(
            f"  {'retention':<22} {_value(f'{plan.retention_days} days', use_color=use_color)}\n"
        )
        if not plan.age_metadata_supported:
            stream.write(f"  {'age metadata':<22} {_value('unavailable', use_color=use_color)}\n")
    stream.write(
        f"  {'schemas scanned':<22} {_value(str(plan.scanned_schema_count), use_color=use_color)}\n"
    )
    stream.write(
        f"  {'schemas skipped':<22} {_value(str(len(plan.skipped_schemas)), use_color=use_color)}\n"
    )
    candidate_count: str = str(len(plan.candidates))
    rendered_candidates: str = (
        yellow(candidate_count)
        if use_color and plan.candidates
        else _value(candidate_count, use_color=use_color)
    )
    stream.write(f"  {'eligible for deletion':<22} {rendered_candidates}\n")
    checkpoint_count: str = str(len(plan.checkpoint_candidates))
    rendered_checkpoints: str = (
        yellow(checkpoint_count)
        if use_color and plan.checkpoint_candidates
        else _value(checkpoint_count, use_color=use_color)
    )
    stream.write(f"  {'checkpoints pruned':<22} {rendered_checkpoints}\n")
    detached_count: str = str(len(plan.detached_virtual_environment_candidates))
    rendered_detached: str = (
        yellow(detached_count)
        if use_color and plan.detached_virtual_environment_candidates
        else _value(detached_count, use_color=use_color)
    )
    stream.write(f"  {'detached VDEs pruned':<22} {rendered_detached}\n")
    expired_vde_count: str = str(len(plan.expired_virtual_environment_candidates))
    rendered_expired_vdes: str = (
        yellow(expired_vde_count)
        if use_color and plan.expired_virtual_environment_candidates
        else _value(expired_vde_count, use_color=use_color)
    )
    stream.write(f"  {'expired VDEs pruned':<22} {rendered_expired_vdes}\n")
    backup_count: str = str(len(plan.state_backup_candidates))
    rendered_backups: str = (
        yellow(backup_count)
        if use_color and plan.state_backup_candidates
        else _value(backup_count, use_color=use_color)
    )
    stream.write(f"  {'state backups pruned':<22} {rendered_backups}\n")
    expired_lock_count: str = str(len(plan.expired_lock_candidates))
    rendered_expired_locks: str = (
        yellow(expired_lock_count)
        if use_color and plan.expired_lock_candidates
        else _value(expired_lock_count, use_color=use_color)
    )
    stream.write(f"  {'expired locks pruned':<22} {rendered_expired_locks}\n")
    skipped_count: str = _value(str(len(plan.skipped_relations)), use_color=use_color)
    stream.write(f"  {'objects skipped':<22} {skipped_count}\n")

    if plan.skipped_schemas:
        stream.write(f"\n{_section('Skipped schemas', use_color=use_color)}\n")
        skipped_schema: JanitorSkippedSchema
        for skipped_schema in plan.skipped_schemas:
            sources: str = ", ".join(skipped_schema.source_names)
            stream.write(
                f"  {_object(skipped_schema.display_name(), use_color=use_color)}  "
                f"{_reason('contains active source ' + sources, use_color=use_color)}\n"
            )

    if plan.candidates:
        stream.write(f"\n{_section('Eligible objects', use_color=use_color)}\n")
        candidate: JanitorDeleteCandidate
        for candidate in plan.candidates:
            stream.write(f"  {_object(candidate.key.display_name(), use_color=use_color)}\n")

    if plan.checkpoint_candidates:
        stream.write(f"\n{_section('Eligible checkpoints', use_color=use_color)}\n")
        checkpoint_candidate: JanitorCheckpointCandidate
        for checkpoint_candidate in plan.checkpoint_candidates:
            stream.write(
                f"  {_object(checkpoint_candidate.checkpoint_id, use_color=use_color)}  "
                f"{_reason(checkpoint_candidate.virtual_environment_name, use_color=use_color)}\n"
            )

    if plan.detached_virtual_environment_candidates:
        stream.write(f"\n{_section('Eligible detached VDEs', use_color=use_color)}\n")
        detached_candidate: JanitorDetachedVirtualEnvironmentCandidate
        for detached_candidate in plan.detached_virtual_environment_candidates:
            stream.write(
                f"  {_object(detached_candidate.virtual_environment_name, use_color=use_color)}  "
                f"{_reason('detached virtual environment', use_color=use_color)}\n"
            )

    if plan.expired_virtual_environment_candidates:
        stream.write(f"\n{_section('Eligible expired VDEs', use_color=use_color)}\n")
        expired_environment_candidate: JanitorExpiredVirtualEnvironmentCandidate
        for expired_environment_candidate in plan.expired_virtual_environment_candidates:
            environment_name: str = expired_environment_candidate.virtual_environment_name
            stream.write(
                f"  {_object(environment_name, use_color=use_color)}  "
                f"{_reason('expired virtual environment', use_color=use_color)}\n"
            )

    if plan.state_backup_candidates:
        stream.write(f"\n{_section('Eligible state backups', use_color=use_color)}\n")
        state_backup_candidate: JanitorStateBackupCandidate
        for state_backup_candidate in plan.state_backup_candidates:
            stream.write(
                f"  {_object(state_backup_candidate.backup_id, use_color=use_color)}  "
                f"{_reason(state_backup_candidate.schema_name, use_color=use_color)}\n"
            )

    if plan.expired_lock_candidates:
        stream.write(f"\n{_section('Eligible expired locks', use_color=use_color)}\n")
        expired_lock_candidate: JanitorExpiredLockCandidate
        for expired_lock_candidate in plan.expired_lock_candidates:
            stream.write(
                f"  {_object(expired_lock_candidate.lock_key, use_color=use_color)}  "
                f"{_reason(expired_lock_candidate.owner_id, use_color=use_color)}\n"
            )

    if plan.skipped_relations:
        stream.write(f"\n{_section('Skipped objects', use_color=use_color)}\n")
        skipped: JanitorSkippedRelation
        for skipped in plan.skipped_relations:
            stream.write(
                f"  {_object(skipped.key.display_name(), use_color=use_color)}  "
                f"{_reason(skipped.reason, use_color=use_color)}\n"
            )
    stream.write("\n")


def confirmation_text(plan: JanitorPlan) -> str:
    """Build the exact confirmation phrase for a janitor plan."""

    state_candidate_count: int = (
        len(plan.checkpoint_candidates)
        + len(plan.detached_virtual_environment_candidates)
        + len(plan.expired_virtual_environment_candidates)
        + len(plan.state_backup_candidates)
        + len(plan.expired_lock_candidates)
    )
    if state_candidate_count == 0:
        return f"delete {len(plan.candidates)} objects from {environment_label(plan)}"
    deletion_count: int = len(plan.candidates) + state_candidate_count
    return f"delete {deletion_count} items from {environment_label(plan)}"


def environment_label(plan: JanitorPlan) -> str:
    """Render the janitor environment label."""

    return plan.environment_name if plan.environment_name is not None else "default"


def _title(text: str, *, use_color: bool) -> str:
    return green_bold(text) if use_color else text


def _section(text: str, *, use_color: bool) -> str:
    return green(text) if use_color else text


def _value(text: str, *, use_color: bool) -> str:
    return blue(text) if use_color else text


def _object(text: str, *, use_color: bool) -> str:
    return blue_bold(text) if use_color else text


def _reason(text: str, *, use_color: bool) -> str:
    if not use_color:
        return text
    return dim(text)
