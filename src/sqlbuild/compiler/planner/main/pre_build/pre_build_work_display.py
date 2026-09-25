"""Plan text for storage and migration work that runs before model builds."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry, PlanOutput
from sqlbuild.presentation.main.append_overflow_line import append_overflow_line
from sqlbuild.presentation.main.visible_entries import visible_entries
from sqlbuild.presentation.models import DisplayOptions


def format_pre_build_work(
    *, lines: list[str], plan: PlanOutput, display_options: DisplayOptions
) -> list[str]:
    """Format retention, table-type, and migration work that runs before model builds."""

    if plan.table_type_entries:
        lines.append("Table type conversions")
        for table_type_entry in visible_entries(
            entries=plan.table_type_entries, options=display_options
        ):
            actual_type: str = table_type_entry.actual_type or "unknown"
            lines.append(
                f"  {table_type_entry.model_name} desired={table_type_entry.desired_type} "
                f"actual={actual_type} source={table_type_entry.source}"
            )
            if table_type_entry.irreversible_warning is not None:
                lines.append(f"    WARNING: {table_type_entry.irreversible_warning}")
        lines = append_overflow_line(
            lines=lines,
            total_count=len(plan.table_type_entries),
            visible_count=len(
                visible_entries(entries=plan.table_type_entries, options=display_options)
            ),
            indent="  ",
            options=display_options,
        )
    if plan.retention_entries:
        lines.append("Retention")
    for entry in plan.retention_entries:
        scope: str = ".".join(
            part
            for part in (entry.request.database, entry.request.schema, entry.request.name)
            if part
        )
        actual: str = "missing" if entry.actual_days is None else f"{entry.actual_days}d"
        effective: str = "missing" if entry.effective_days is None else f"{entry.effective_days}d"
        lines.append(
            f"  {scope} desired={entry.request.desired_days}d actual={actual} "
            f"effective={effective} source={entry.source} direction={entry.direction.value} "
            f"phase={entry.phase.value}"
        )
        if entry.irreversible_warning is not None:
            lines.append(f"    WARNING: {entry.irreversible_warning}")
    return _format_model_migrations(lines=lines, plan=plan, display_options=display_options)


def _format_model_migrations(
    *, lines: list[str], plan: PlanOutput, display_options: DisplayOptions
) -> list[str]:
    title: str
    renamed: bool
    for title, renamed in (("Migrations", False), ("Renamed", True)):
        entries: tuple[ModelMigrationPlanEntry, ...] = tuple(
            entry
            for entry in plan.migration_entries
            if (entry.decision == MigrationDecision.RENAMED) is renamed
        )
        if not entries:
            continue
        lines.append(f"{title} ({len(entries)})")
        visible: Sequence[ModelMigrationPlanEntry] = visible_entries(
            entries=entries, options=display_options
        )
        entry: ModelMigrationPlanEntry
        for entry in visible:
            lines.extend(_migration_lines(entry))
        lines = append_overflow_line(
            lines=lines,
            total_count=len(entries),
            visible_count=len(visible),
            indent="  ",
            options=display_options,
        )
    return lines


def _migration_lines(entry: ModelMigrationPlanEntry) -> list[str]:
    origin: str = entry.origin.qualified_name or entry.origin.name
    destination: str = entry.destination.qualified_name or entry.destination.name
    if entry.decision == MigrationDecision.RENAMED:
        return [f"  {entry.model_name}  {origin} -> {destination}  (identity handed over)"]
    rows: list[str] = [f"  {entry.model_name}  {entry.decision.label}  {origin} -> {destination}"]
    if entry.decision.checks_compatibility:
        rows.append(f"    compatibility  {entry.compatibility.value}")
    if entry.transfer is not None:
        details: tuple[str | None, ...] = (
            entry.transfer.label,
            entry.storage_transition,
            None if entry.promotion is None else f"promote by {entry.promotion.label}",
        )
        rows.append(f"    transfer  {', '.join(detail for detail in details if detail)}")
    if entry.discovery != MigrationDiscovery.MANUAL:
        rows.append(f"    discovery  {entry.discovery.value}")
    if entry.completed_at is not None:
        rows.append(
            f"    completed  {entry.completed_at.isoformat()} on target "
            f"'{entry.target_name or 'default'}'"
        )
    rows.extend(f"    ! {finding}" for finding in entry.compatibility_findings)
    return rows
