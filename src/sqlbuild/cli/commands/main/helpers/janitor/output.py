"""Janitor command output helpers."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorPlan,
    JanitorSkippedRelation,
    JanitorSkippedSchema,
)


def write_disabled(stream: TextIO) -> None:
    """Write disabled janitor guidance."""

    stream.write(
        "Janitor is disabled for this project.\n\n"
        "Enable it with:\n\n"
        "janitor:\n"
        "  enabled: true\n"
        "  retention_days: 30\n"
    )


def write_plan(*, plan: JanitorPlan, stream: TextIO) -> None:
    """Write a janitor preview."""

    env_label: str = environment_label(plan)
    stream.write(f"Janitor preview for {env_label}\n\n")
    if plan.retention_days == 0:
        stream.write("Retention: disabled (0 days)\n")
        stream.write("Age metadata will not be checked.\n")
    else:
        stream.write(f"Retention: {plan.retention_days} days\n")
        if not plan.age_metadata_supported:
            stream.write("Adapter does not expose relation age metadata.\n")
    stream.write(f"Schemas scanned: {plan.scanned_schema_count}\n")
    stream.write(f"Schemas skipped: {len(plan.skipped_schemas)}\n")
    stream.write(f"Objects eligible for deletion: {len(plan.candidates)}\n")
    stream.write(f"Objects skipped: {len(plan.skipped_relations)}\n")

    if plan.skipped_schemas:
        stream.write("\nSkipped schemas\n")
        skipped_schema: JanitorSkippedSchema
        for skipped_schema in plan.skipped_schemas:
            sources: str = ", ".join(skipped_schema.source_names)
            stream.write(f"- {skipped_schema.display_name()}: contains active source {sources}\n")

    if plan.candidates:
        stream.write("\nEligible objects\n")
        candidate: JanitorDeleteCandidate
        for candidate in plan.candidates:
            stream.write(f"- {candidate.key.display_name()}\n")

    if plan.skipped_relations:
        stream.write("\nSkipped objects\n")
        skipped: JanitorSkippedRelation
        for skipped in plan.skipped_relations:
            stream.write(f"- {skipped.key.display_name()}: {skipped.reason}\n")
    stream.write("\n")


def confirmation_text(plan: JanitorPlan) -> str:
    """Build the exact confirmation phrase for a janitor plan."""

    return f"delete {len(plan.candidates)} objects from {environment_label(plan)}"


def environment_label(plan: JanitorPlan) -> str:
    """Render the janitor environment label."""

    return plan.environment_name if plan.environment_name is not None else "default"
