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
from sqlbuild.presentation.classes.cli_style import CliStyle


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


def _write_plan_summary(*, plan: JanitorPlan, stream: TextIO, style: CliStyle) -> None:
    if plan.retention_days == 0:
        stream.write(f"  {'retention':<22} {style.accent('disabled (0 days)')}\n")
        stream.write(f"  {'age metadata':<22} {style.accent('not checked')}\n")
    else:
        stream.write(f"  {'retention':<22} {style.accent(f'{plan.retention_days} days')}\n")
        if not plan.age_metadata_supported:
            stream.write(f"  {'age metadata':<22} {style.accent('unavailable')}\n")
    stream.write(f"  {'schemas scanned':<22} {style.accent(str(plan.scanned_schema_count))}\n")
    stream.write(f"  {'schemas skipped':<22} {style.accent(str(len(plan.skipped_schemas)))}\n")
    _write_count_row(
        stream=stream,
        style=style,
        label="reported objects" if plan.direct_mode else "eligible for deletion",
        items=plan.candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="checkpoints pruned",
        items=plan.checkpoint_candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="detached VDEs pruned",
        items=plan.detached_virtual_environment_candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="expired VDEs pruned",
        items=plan.expired_virtual_environment_candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="state backups pruned",
        items=plan.state_backup_candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="expired locks pruned",
        items=plan.expired_lock_candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="direct state pruned",
        items=plan.direct_state_prune_candidates,
    )
    _write_count_row(
        stream=stream,
        style=style,
        label="virtual state pruned",
        items=plan.virtual_state_prune_candidates,
    )
    skipped_count: str = style.accent(str(len(plan.skipped_relations)))
    stream.write(f"  {'objects skipped':<22} {skipped_count}\n")


def _write_count_row(
    *, stream: TextIO, style: CliStyle, label: str, items: tuple[object, ...]
) -> None:
    count: str = str(len(items))
    rendered: str = style.warning(count) if items else style.accent(count)
    stream.write(f"  {label:<22} {rendered}\n")


def write_plan(*, plan: JanitorPlan, stream: TextIO, use_color: bool = False) -> None:
    """Write a janitor preview."""

    style: CliStyle = CliStyle(use_color=use_color)
    env_label: str = environment_label(plan)
    rendered_env: str = style.object_name(env_label)
    stream.write(f"{style.title('Janitor preview')}  {rendered_env}\n\n")
    _write_plan_summary(plan=plan, stream=stream, style=style)

    if plan.blocked_schemas:
        stream.write(f"\n{style.error_strong('Janitor blocked')}\n")
        stream.write(
            f"  {style.error('Managed target schemas contain active configured sources.')}\n"
        )
        for blocked_schema in plan.blocked_schemas:
            sources: str = ", ".join(blocked_schema.source_names)
            stream.write(
                f"  {style.object_name(blocked_schema.display_name())}  "
                f"{style.error_muted('active sources: ' + sources)}\n"
            )
            for candidate in blocked_schema.suppressed_candidates:
                suppressed: str = f"suppressed deletion: {candidate.key.display_name()}"
                stream.write(f"    {style.error_muted(suppressed)}\n")
        stream.write(f"  {style.error('No janitor actions will be performed.')}\n")

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
        heading: str = "Report-only objects" if plan.direct_mode else "Eligible objects"
        stream.write(f"\n{style.success(heading)}\n")
        candidate: JanitorDeleteCandidate
        for candidate in plan.candidates:
            reason: str = "  direct mode does not delete relations" if plan.direct_mode else ""
            stream.write(
                f"  {style.object_name(candidate.key.display_name())}{style.muted(reason)}\n"
            )

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

    if plan.direct_state_prune_candidates:
        stream.write(f"\n{style.success('Eligible direct state pruning')}\n")
        for direct_state_candidate in plan.direct_state_prune_candidates:
            stream.write(
                f"  {style.object_name(direct_state_candidate.display_name())}  "
                f"{style.muted(f'keep latest {direct_state_candidate.retain_versions}')}\n"
            )

    if plan.virtual_state_prune_candidates:
        stream.write(f"\n{style.success('Eligible virtual state pruning')}\n")
        for virtual_state_candidate in plan.virtual_state_prune_candidates:
            stream.write(
                f"  {style.object_name(virtual_state_candidate.display_name())}  "
                f"{style.muted(virtual_state_candidate.reason)}\n"
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
        + len(plan.direct_state_prune_candidates)
        + len(plan.virtual_state_prune_candidates)
    )
    if state_candidate_count == 0:
        deletion_count: int = 0 if plan.direct_mode else len(plan.candidates)
        return f"delete {deletion_count} objects from {environment_label(plan)}"
    physical_deletion_count: int = 0 if plan.direct_mode else len(plan.candidates)
    deletion_count: int = physical_deletion_count + state_candidate_count
    return f"delete {deletion_count} items from {environment_label(plan)}"


def environment_label(plan: JanitorPlan) -> str:
    """Render the janitor environment label."""

    return plan.target_name if plan.target_name is not None else "default"
