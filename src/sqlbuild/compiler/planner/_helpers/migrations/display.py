"""Plan text for model migrations and identity handovers."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlbuild.compiler.migrations.types import (
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
)
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry, PlanOutput
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.append_overflow_line import append_overflow_line
from sqlbuild.presentation.main.count_header import count_header_style
from sqlbuild.presentation.main.visible_entries import visible_entries
from sqlbuild.presentation.models import DisplayOptions


def format_model_migrations(
    *, lines: list[str], plan: PlanOutput, display_options: DisplayOptions
) -> list[str]:
    """Format declared and discovered model migrations, then identity handovers."""

    result: list[str] = list(lines)
    style: CliStyle = CliStyle(use_color=True)
    header_style: Callable[[str], str] = count_header_style(
        style=style, title_style=style.plan_section
    )
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
        result.append(header_style(f"{title} ({len(entries)})"))
        visible: Sequence[ModelMigrationPlanEntry] = visible_entries(
            entries=entries, options=display_options
        )
        entry: ModelMigrationPlanEntry
        for entry in visible:
            result.extend(_migration_lines(entry=entry, style=style))
        result = append_overflow_line(
            lines=result,
            total_count=len(entries),
            visible_count=len(visible),
            indent="  ",
            options=display_options,
        )
    return result


def _migration_lines(*, entry: ModelMigrationPlanEntry, style: CliStyle) -> list[str]:
    origin: str = entry.origin.qualified_name or entry.origin.name
    destination: str = entry.destination.qualified_name or entry.destination.name
    relation_move: str = f"{style.muted(f'{origin} ->')} {destination}"
    name: str = style.object_name(entry.model_name)
    if entry.decision == MigrationDecision.RENAMED:
        return [f"  {name}  {relation_move}  {style.muted('(identity handed over)')}"]
    decision: str = _decision_text(decision=entry.decision, style=style)
    rows: list[str] = [f"  {name}  {decision}  {relation_move}"]
    if entry.decision.checks_compatibility:
        rows.append(
            _property_row(
                label="compatibility",
                value=_compatibility_text(compatibility=entry.compatibility, style=style),
                style=style,
            )
        )
    if entry.transfer is not None:
        details: tuple[str | None, ...] = (
            entry.transfer.label
            + (
                ""
                if entry.transfer_fallback is None
                else f" ({entry.transfer_fallback.label} if refused)"
            ),
            entry.storage_transition,
            None if entry.promotion is None else f"promote by {entry.promotion.label}",
        )
        rows.append(
            _property_row(
                label="transfer",
                value=", ".join(detail for detail in details if detail),
                style=style,
            )
        )
    if entry.discovery != MigrationDiscovery.MANUAL:
        rows.append(_property_row(label="discovery", value=entry.discovery.value, style=style))
    if entry.completed_at is not None:
        rows.append(
            _property_row(
                label="completed",
                value=(
                    f"{entry.completed_at.isoformat()} on target '{entry.target_name or 'default'}'"
                ),
                style=style,
            )
        )
    blocking: bool = (
        entry.decision.blocks_build or entry.compatibility == MigrationCompatibility.INCOMPATIBLE
    )
    finding_style: Callable[[str], str] = style.error if blocking else style.warning
    rows.extend(f"    {finding_style(f'! {finding}')}" for finding in entry.compatibility_findings)
    return rows


def _property_row(*, label: str, value: str, style: CliStyle) -> str:
    return f"    {style.muted(label)}  {value}"


def _decision_text(*, decision: MigrationDecision, style: CliStyle) -> str:
    if decision.blocks_build:
        return style.error_strong(decision.label)
    if decision in (MigrationDecision.SUPERSEDED_REPLACE, MigrationDecision.FORCED_REPLACE):
        return style.warning_strong(decision.label)
    if decision == MigrationDecision.DONE:
        return style.muted(decision.label)
    return style.accent_strong(decision.label)


def _compatibility_text(*, compatibility: MigrationCompatibility, style: CliStyle) -> str:
    if compatibility == MigrationCompatibility.COMPATIBLE:
        return style.success(compatibility.value)
    if compatibility == MigrationCompatibility.INCOMPATIBLE:
        return style.error(compatibility.value)
    return compatibility.value
