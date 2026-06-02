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
from sqlbuild.shared.helpers.cli_style import CliStyle


def write_disabled(*, stream: TextIO, use_color: bool = False) -> None:
    """Write disabled janitor guidance."""

    style: CliStyle = CliStyle(use_color=use_color)
    disabled_detail: str = (
        "Janitor is opt-in. It previews stale warehouse objects and asks before deleting anything."
    )
    stream.write(
        f"{style.warning_strong('Janitor is disabled for this project.')}\n\n"
        f"{style.warning(disabled_detail)}\n\n"
        f"Add this block to {style.object_name('sqlbuild_project.toml')}:\n\n"
        "janitor:\n"
        "  enabled: true\n"
        "  retention_days: 30\n\n"
        "After enabling, run janitor again to preview cleanup:\n"
        f"  {style.accent('sqb janitor')}\n"
    )


def write_plan(*, plan: JanitorPlan, stream: TextIO, use_color: bool = False) -> None:
    """Write a janitor preview."""

    style: CliStyle = CliStyle(use_color=use_color)
    env_label: str = environment_label(plan)
    rendered_env: str = style.object_name(env_label)
    stream.write(f"{style.title('Janitor preview')}  {rendered_env}\n\n")
    if plan.retention_days == 0:
        stream.write(f"  {'retention':<22} {style.accent('disabled (0 days)')}\n")
        stream.write(f"  {'age metadata':<22} {style.accent('not checked')}\n")
    else:
        stream.write(f"  {'retention':<22} {style.accent(f'{plan.retention_days} days')}\n")
        if not plan.age_metadata_supported:
            stream.write(f"  {'age metadata':<22} {style.accent('unavailable')}\n")
    stream.write(f"  {'schemas scanned':<22} {style.accent(str(plan.scanned_schema_count))}\n")
    stream.write(f"  {'schemas skipped':<22} {style.accent(str(len(plan.skipped_schemas)))}\n")
    candidate_count: str = str(len(plan.candidates))
    rendered_candidates: str = (
        style.warning(candidate_count) if plan.candidates else style.accent(candidate_count)
    )
    stream.write(f"  {'eligible for deletion':<22} {rendered_candidates}\n")
    checkpoint_count: str = str(len(plan.checkpoint_candidates))
    rendered_checkpoints: str = (
        style.warning(checkpoint_count)
        if plan.checkpoint_candidates
        else style.accent(checkpoint_count)
    )
    stream.write(f"  {'checkpoints pruned':<22} {rendered_checkpoints}\n")
    detached_count: str = str(len(plan.detached_virtual_environment_candidates))
    rendered_detached: str = (
        style.warning(detached_count)
        if plan.detached_virtual_environment_candidates
        else style.accent(detached_count)
    )
    stream.write(f"  {'detached VDEs pruned':<22} {rendered_detached}\n")
    expired_vde_count: str = str(len(plan.expired_virtual_environment_candidates))
    rendered_expired_vdes: str = (
        style.warning(expired_vde_count)
        if plan.expired_virtual_environment_candidates
        else style.accent(expired_vde_count)
    )
    stream.write(f"  {'expired VDEs pruned':<22} {rendered_expired_vdes}\n")
    backup_count: str = str(len(plan.state_backup_candidates))
    rendered_backups: str = (
        style.warning(backup_count) if plan.state_backup_candidates else style.accent(backup_count)
    )
    stream.write(f"  {'state backups pruned':<22} {rendered_backups}\n")
    expired_lock_count: str = str(len(plan.expired_lock_candidates))
    rendered_expired_locks: str = (
        style.warning(expired_lock_count)
        if plan.expired_lock_candidates
        else style.accent(expired_lock_count)
    )
    stream.write(f"  {'expired locks pruned':<22} {rendered_expired_locks}\n")
    skipped_count: str = style.accent(str(len(plan.skipped_relations)))
    stream.write(f"  {'objects skipped':<22} {skipped_count}\n")

    if plan.skipped_schemas:
        stream.write(f"\n{style.success('Skipped schemas')}\n")
        skipped_schema: JanitorSkippedSchema
        for skipped_schema in plan.skipped_schemas:
            sources: str = ", ".join(skipped_schema.source_names)
            stream.write(
                f"  {style.object_name(skipped_schema.display_name())}  "
                f"{style.muted('contains active source ' + sources)}\n"
            )

    if plan.candidates:
        stream.write(f"\n{style.success('Eligible objects')}\n")
        candidate: JanitorDeleteCandidate
        for candidate in plan.candidates:
            stream.write(f"  {style.object_name(candidate.key.display_name())}\n")

    if plan.checkpoint_candidates:
        stream.write(f"\n{style.success('Eligible checkpoints')}\n")
        checkpoint_candidate: JanitorCheckpointCandidate
        for checkpoint_candidate in plan.checkpoint_candidates:
            stream.write(
                f"  {style.object_name(checkpoint_candidate.checkpoint_id)}  "
                f"{style.muted(checkpoint_candidate.virtual_environment_name)}\n"
            )

    if plan.detached_virtual_environment_candidates:
        stream.write(f"\n{style.success('Eligible detached VDEs')}\n")
        detached_candidate: JanitorDetachedVirtualEnvironmentCandidate
        for detached_candidate in plan.detached_virtual_environment_candidates:
            stream.write(
                f"  {style.object_name(detached_candidate.virtual_environment_name)}  "
                f"{style.muted('detached virtual environment')}\n"
            )

    if plan.expired_virtual_environment_candidates:
        stream.write(f"\n{style.success('Eligible expired VDEs')}\n")
        expired_environment_candidate: JanitorExpiredVirtualEnvironmentCandidate
        for expired_environment_candidate in plan.expired_virtual_environment_candidates:
            target_name: str = expired_environment_candidate.virtual_environment_name
            stream.write(
                f"  {style.object_name(target_name)}  "
                f"{style.muted('expired virtual environment')}\n"
            )

    if plan.state_backup_candidates:
        stream.write(f"\n{style.success('Eligible state backups')}\n")
        state_backup_candidate: JanitorStateBackupCandidate
        for state_backup_candidate in plan.state_backup_candidates:
            stream.write(
                f"  {style.object_name(state_backup_candidate.backup_id)}  "
                f"{style.muted(state_backup_candidate.schema_name)}\n"
            )

    if plan.expired_lock_candidates:
        stream.write(f"\n{style.success('Eligible expired locks')}\n")
        expired_lock_candidate: JanitorExpiredLockCandidate
        for expired_lock_candidate in plan.expired_lock_candidates:
            stream.write(
                f"  {style.object_name(expired_lock_candidate.lock_key)}  "
                f"{style.muted(expired_lock_candidate.owner_id)}\n"
            )

    if plan.skipped_relations:
        stream.write(f"\n{style.success('Skipped objects')}\n")
        skipped: JanitorSkippedRelation
        for skipped in plan.skipped_relations:
            stream.write(
                f"  {style.object_name(skipped.key.display_name())}  "
                f"{style.muted(skipped.reason)}\n"
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

    return plan.target_name if plan.target_name is not None else "default"
