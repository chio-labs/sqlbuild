"""Plan text for model migrations and identity handovers."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
    OldNameViewAction,
)
from sqlbuild.compiler.planner.constants import MANUAL_RENAME_HINT
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanEntry,
    ModelMigrationPlanEntry,
    OldNameViewPlanEntry,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.append_overflow_line import append_overflow_line
from sqlbuild.presentation.main.count_header import count_header_style
from sqlbuild.presentation.main.tree_connector import tree_connector
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
    entries: tuple[ModelMigrationPlanEntry, ...] = plan.migration_entries
    old_names: dict[str, OldNameViewPlanEntry] = {
        entry.model_name: entry for entry in plan.old_name_view_entries
    }
    materializations: dict[str, str] = {
        entry.name: str(entry.materialization_type) for entry in plan.model_entries
    }
    if entries:
        result.append(header_style(f"Migrations ({len(entries)})"))
        visible: Sequence[ModelMigrationPlanEntry] = visible_entries(
            entries=entries, options=display_options
        )
        entry: ModelMigrationPlanEntry
        for entry in visible:
            result.extend(
                _migration_lines(
                    entry=entry,
                    style=style,
                    old_name=old_names.get(entry.model_name),
                    materialization=materializations.get(entry.model_name),
                )
            )
        result = append_overflow_line(
            lines=result,
            total_count=len(entries),
            visible_count=len(visible),
            indent="  ",
            options=display_options,
        )
    result = _format_resumed_old_names(
        lines=result,
        plan=plan,
        style=style,
        header_style=header_style,
    )
    return _format_column_migrations(
        lines=result, plan=plan, style=style, header_style=header_style
    )


def _format_resumed_old_names(
    *,
    lines: list[str],
    plan: PlanOutput,
    style: CliStyle,
    header_style: Callable[[str], str],
) -> list[str]:
    """Format old-name steps that resume a move no longer listed as a migration."""

    migrated: frozenset[str] = frozenset(entry.model_name for entry in plan.migration_entries)
    resumed: tuple[OldNameViewPlanEntry, ...] = tuple(
        entry for entry in plan.old_name_view_entries if entry.model_name not in migrated
    )
    if not resumed:
        return lines
    result: list[str] = list(lines)
    result.append(header_style(f"Old names ({len(resumed)})"))
    entry: OldNameViewPlanEntry
    for entry in resumed:
        origin: str = entry.origin.qualified_name or entry.origin.name
        destination: str = entry.destination.qualified_name or entry.destination.name
        result.append(
            f"  {style.object_name(entry.model_name)}  {style.muted(f'{origin} ->')} {destination}"
        )
        result.extend(old_name_rows(entry=entry, style=style))
    return result


def old_name_rows(*, entry: OldNameViewPlanEntry, style: CliStyle) -> list[str]:
    """Render the old name of a migration as a leaf with one fact per nested row."""

    origin: str = entry.origin.qualified_name or entry.origin.name
    facts: list[tuple[str, str]] = old_name_facts(entry)
    rows: list[str] = [_property_row(label="old name", value=origin, style=style)]
    index: int
    label: str
    value: str
    for index, (label, value) in enumerate(facts):
        connector: str = tree_connector(style=style, last=index == len(facts) - 1)
        rows.append(f"        {connector} {style.muted(label)}  {value}")
    return rows


def old_name_facts(entry: OldNameViewPlanEntry) -> list[tuple[str, str]]:
    """Return what happens at a migrated model's old name, one labelled fact per row."""

    if entry.action == OldNameViewAction.NONE:
        return [("left for janitor", entry.reason or "no compatibility view")]
    until: str = "" if entry.expires_at is None else f"until {entry.expires_at:%Y-%m-%d}"
    view: str = f"live {until}".strip() if entry.action == OldNameViewAction.LIVE else until
    facts: list[tuple[str, str]] = [("view", view)]
    if entry.column_aliases:
        facts.append(("columns", ", ".join(f"{old} <- {new}" for old, new in entry.column_aliases)))
    if entry.grants_supported:
        facts.append(("grants", _grants_text(entry)))
    archived: str = (
        "already archived" if entry.action == OldNameViewAction.VIEW_ONLY else "archived"
    )
    facts.append(("old table", archived))
    return facts


def _grants_text(entry: OldNameViewPlanEntry) -> str:
    if entry.grants_copied is None:
        return "copied from the old table"
    return f"{entry.grants_copied} copied from the old table"


def _format_column_migrations(
    *,
    lines: list[str],
    plan: PlanOutput,
    style: CliStyle,
    header_style: Callable[[str], str],
) -> list[str]:
    """Format in-place column renames grouped under the model whose table they change."""

    entries: tuple[ColumnMigrationPlanEntry, ...] = plan.column_migration_entries
    if not entries:
        return lines
    result: list[str] = list(lines)
    result.append(header_style(f"Column migrations ({len(entries)})"))
    model_names: tuple[str, ...] = tuple(dict.fromkeys(entry.model_name for entry in entries))
    model_name: str
    for model_name in model_names:
        result.append(f"  {style.object_name(model_name)}  {style.muted('migrate columns')}")
        entry: ColumnMigrationPlanEntry
        for entry in entries:
            if entry.model_name == model_name:
                result.append(f"    {_column_migration_text(entry=entry, style=style)}")
    return result


def _column_migration_text(*, entry: ColumnMigrationPlanEntry, style: CliStyle) -> str:
    rename: str = f"{entry.origin_column} -> {entry.destination_column}"
    decision: str
    if entry.blocks_build:
        decision = style.error_strong(entry.decision.label)
    elif entry.origin_missing:
        decision = style.warning_strong(entry.decision.label)
    elif entry.decision == ColumnMigrationDecision.DONE:
        decision = style.muted(entry.decision.label)
    else:
        decision = style.accent_strong(entry.decision.label)
    details: list[str] = []
    if entry.discovery != MigrationDiscovery.MANUAL:
        details.append(entry.discovery.value)
    if entry.decision == ColumnMigrationDecision.DONE and entry.completed_at is not None:
        details.append(f"completed {entry.completed_at.isoformat()}")
    suffix: str = f"  {style.muted(f'({", ".join(details)})')}" if details else ""
    return f"{rename}  {decision}{suffix}"


def _migration_lines(
    *,
    entry: ModelMigrationPlanEntry,
    style: CliStyle,
    old_name: OldNameViewPlanEntry | None,
    materialization: str | None,
) -> list[str]:
    origin: str = entry.origin.qualified_name or entry.origin.name
    destination: str = entry.destination.qualified_name or entry.destination.name
    relation_move: str = f"{style.muted(f'{origin} ->')} {destination}"
    name: str = style.object_name(entry.model_name)
    decision: str = _decision_text(entry=entry, style=style)
    if entry.decision == MigrationDecision.RENAMED:
        decision = (
            style.muted(MigrationDecision.DONE.label)
            if entry.completed_at is not None
            else style.accent_strong(MigrationDecision.MIGRATE.label)
        )
    rows: list[str] = [f"  {name}  {decision}  {relation_move}"]
    if entry.decision == MigrationDecision.RENAMED and entry.completed_at is None:
        rows.append(
            _property_row(
                label="transfer", value=identity_transfer_label(materialization), style=style
            )
        )
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
    if entry.discovery == MigrationDiscovery.AUTOMATIC and entry.completed_at is None:
        rows.append(_property_row(label="hint", value=MANUAL_RENAME_HINT, style=style))
    if entry.completed_at is not None:
        rows.append(
            _property_row(
                label="completed",
                value=f"{entry.completed_at.isoformat()} on target '{entry.target_label}'",
                style=style,
            )
        )
    if old_name is not None:
        rows.extend(old_name_rows(entry=old_name, style=style))
    blocking: bool = entry.blocks_build or (
        entry.compatibility == MigrationCompatibility.INCOMPATIBLE
    )
    finding_style: Callable[[str], str] = style.error if blocking else style.warning
    rows.extend(f"    {finding_style(f'! {finding}')}" for finding in entry.compatibility_findings)
    return rows


def identity_transfer_label(materialization: str | None) -> str:
    """Describe how a renamed table or view reaches its new name."""

    if materialization == MaterializationType.VIEW:
        return "recreate (view)"
    return "rebuild (table)"


def _property_row(*, label: str, value: str, style: CliStyle) -> str:
    return f"    {style.muted(label)}  {value}"


def _decision_text(*, entry: ModelMigrationPlanEntry, style: CliStyle) -> str:
    decision: MigrationDecision = entry.decision
    if entry.blocks_build and decision.blocks_build:
        return style.error_strong(decision.label)
    if entry.origin_missing:
        return style.warning_strong(decision.label)
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
