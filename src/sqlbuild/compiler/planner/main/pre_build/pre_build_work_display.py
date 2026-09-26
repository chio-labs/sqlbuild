"""Plan text for storage and migration work that runs before model builds."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.migrations.display import format_model_migrations
from sqlbuild.compiler.planner.models import PlanOutput
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
    return format_model_migrations(lines=lines, plan=plan, display_options=display_options)
