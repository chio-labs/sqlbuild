"""Janitor command output helpers."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.executor.janitor.models import (
    JanitorCheckpointCandidate,
    JanitorDeleteCandidate,
    JanitorPlan,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
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

    if not plan.checkpoint_candidates:
        return f"delete {len(plan.candidates)} objects from {environment_label(plan)}"
    deletion_count: int = len(plan.candidates) + len(plan.checkpoint_candidates)
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
    if "referenced by a retained virtual checkpoint" in text:
        return green(text)
    return dim(text)
