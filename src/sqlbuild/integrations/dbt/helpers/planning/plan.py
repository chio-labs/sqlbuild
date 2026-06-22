"""Plan construction and formatting for dbt interop commands."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Sequence

from sqlbuild.cli.commands.main.plan_format import format_plan
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import (
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtModelPlanEntry,
    DbtModelPlanningResult,
    DbtReusePlanEntry,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtInteropSkipReason,
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReusePlanAction,
    DbtReusePlanReason,
    DbtSupportedResourceType,
)
from sqlbuild.shared.helpers.alignment import format_aligned_name_value, resolve_name_column_width
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.display import DisplayOptions, append_overflow_line, visible_entries
from sqlbuild.shared.helpers.query_diff import format_query_diff

_ANSI_ESCAPE_PATTERN: re.Pattern[str] = re.compile(r"\033\[[0-9;]*m")


def build_dbt_interop_plan(
    *,
    command: DbtInteropCommand | str,
    dbt_command_argv: Sequence[str],
    dbt_ls_nodes: Sequence[DbtLsNode],
    sqlbuild_command_argvs: Sequence[Sequence[str]],
    selection: DbtInteropSelectionResult,
    dbt_required_selector_terms: Sequence[str] = (),
    supplemental_dbt_command_argvs: Sequence[Sequence[str]] = (),
    warnings: Sequence[str] = (),
    sqlbuild_plan_output: PlanOutput | None = None,
    dbt_model_plan: DbtModelPlanningResult | None = None,
    dbt_reuse_plan: DbtReusePlanningResult | None = None,
) -> DbtInteropPlan:
    """Build a display-ready plan from dbt preflight and SQLBuild selection results."""

    normalized_command: DbtInteropCommand = DbtInteropCommand(command)
    dbt_selected_unique_ids: tuple[str, ...] = tuple(
        sorted(node.unique_id for node in dbt_ls_nodes)
    )
    sqlbuild_model_names: tuple[str, ...] = selection.sqlbuild_model_names
    dbt_has_work: bool = bool(dbt_selected_unique_ids)
    if normalized_command != DbtInteropCommand.TEST:
        dbt_has_work = bool(dbt_selected_unique_ids or selection.dbt_required_unique_ids)
    sqlbuild_has_work: bool = bool(sqlbuild_model_names)
    resolved_warnings: tuple[str, ...] = tuple(warnings)
    no_match_warning: str = "No dbt or SQLBuild resources matched the selection."
    if not dbt_has_work and not sqlbuild_has_work and no_match_warning not in resolved_warnings:
        resolved_warnings = (
            *resolved_warnings,
            no_match_warning,
        )
    return DbtInteropPlan(
        command=normalized_command,
        dbt_command_argv=tuple(dbt_command_argv),
        dbt_selected_nodes=tuple(dbt_ls_nodes),
        dbt_selected_unique_ids=dbt_selected_unique_ids,
        sqlbuild_command_argvs=tuple(tuple(argv) for argv in sqlbuild_command_argvs),
        selection=selection,
        sqlbuild_plan_output=sqlbuild_plan_output,
        dbt_model_plan=dbt_model_plan,
        dbt_reuse_plan=dbt_reuse_plan,
        dbt_required_selector_terms=tuple(dbt_required_selector_terms),
        supplemental_dbt_command_argvs=tuple(
            tuple(argv) for argv in supplemental_dbt_command_argvs
        ),
        dbt_skip_reason=None if dbt_has_work else DbtInteropSkipReason.NO_DBT_WORK,
        sqlbuild_skip_reason=None if sqlbuild_has_work else DbtInteropSkipReason.NO_SQLBUILD_WORK,
        warnings=resolved_warnings,
    )


def format_dbt_interop_plan(
    plan: DbtInteropPlan,
    *,
    use_color: bool = True,
    display_options: DisplayOptions | None = None,
) -> str:
    """Format a dbt interop plan for human CLI output."""

    resolved_display_options: DisplayOptions = display_options or DisplayOptions()
    if plan.command == DbtInteropCommand.TEST:
        return _format_dbt_test_plan(
            plan, use_color=use_color, display_options=resolved_display_options
        )
    lines: list[str] = []
    dbt_selected_count: int = len(plan.dbt_selected_unique_ids)
    dbt_required_count: int = len(plan.selection.dbt_required_unique_ids)
    sqlbuild_count: int = len(plan.selection.sqlbuild_model_names)
    selected_count: int = (
        len(frozenset((*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids)))
        + sqlbuild_count
    )
    style: CliStyle = CliStyle(use_color=True)
    lines.append(
        style.success_strong(
            "Plan ready ("
            + _format_plan_ready_resource_counts(
                dbt_selected_count=dbt_selected_count,
                dbt_required_count=dbt_required_count,
                sqlbuild_count=sqlbuild_count,
                total_count=selected_count,
            )
            + ")"
        )
    )
    lines.append("")
    _format_dbt_section(lines, plan, display_options=resolved_display_options)
    _format_anchor_section(lines, plan, display_options=resolved_display_options)
    lines.append("")
    _format_sqlbuild_section(
        lines, plan, use_color=use_color, display_options=resolved_display_options
    )
    _format_path_translation_section(lines, plan)
    _format_warning_section(lines, plan)
    result: str = "\n".join(lines)
    return result if use_color else _strip_ansi(result)


def format_dbt_interop_plan_json(plan: DbtInteropPlan) -> str:
    """Serialize a dbt interop plan to stable JSON."""

    result: dict[str, object] = {
        "command": plan.command.value,
        "dbt": {
            "argv": list(plan.dbt_command_argv),
            "supplemental_argvs": [list(argv) for argv in plan.supplemental_dbt_command_argvs],
            "selected_unique_ids": list(plan.dbt_selected_unique_ids),
            "required_unique_ids": list(plan.selection.dbt_required_unique_ids),
            "required_selector_terms": list(plan.dbt_required_selector_terms),
            "non_model_run_unique_ids": list(plan.dbt_non_model_run_unique_ids),
            "pruned_seed_unique_ids": list(plan.dbt_pruned_seed_unique_ids),
            "pruned_test_unique_ids": list(plan.dbt_pruned_test_unique_ids),
            "skipped": plan.dbt_skip_reason is not None,
            "skip_reason": plan.dbt_skip_reason.value if plan.dbt_skip_reason is not None else None,
            "model_plan": _format_dbt_model_plan_json(plan),
            "reuse_plan": _format_dbt_reuse_plan_json(plan),
            "dependency_baseline_plan": _format_dbt_dependency_baseline_plan_json(plan),
        },
        "sqlbuild": {
            "argvs": [list(argv) for argv in plan.sqlbuild_command_argvs],
            "selected_models": list(plan.selection.sqlbuild_model_names),
            "skipped": plan.sqlbuild_skip_reason is not None,
            "skip_reason": plan.sqlbuild_skip_reason.value
            if plan.sqlbuild_skip_reason is not None
            else None,
        },
        "anchors": [
            {
                "term": term,
                "unique_ids": list(plan.selection.dbt_anchor_unique_ids_by_term.get(term, ())),
            }
            for term in plan.selection.dbt_anchor_terms
        ],
        "path_translations": [
            {"from": original, "to": translated}
            for original, translated in plan.selection.path_translations
        ],
        "warnings": list(plan.warnings),
    }
    return json.dumps(result, indent=2)


def _format_dbt_section(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    style: CliStyle = CliStyle(use_color=True)
    dbt_selected_count: int = len(plan.dbt_selected_unique_ids)
    dbt_required_count: int = len(plan.selection.dbt_required_unique_ids)
    lines.append(
        style.dbt_section(
            "dbt ("
            + _format_dbt_section_resource_counts(
                selected_count=dbt_selected_count,
                required_count=dbt_required_count,
            )
            + ")"
        )
    )
    _format_dbt_resource_summary(lines, plan)
    if plan.dbt_skip_reason is not None:
        lines.append(style.muted(f"  skipped: {_dbt_skip_reason_label(plan.dbt_skip_reason)}"))
        if plan.dbt_model_plan is not None:
            _format_dbt_model_plan(lines, plan, display_options=display_options)
            _format_dbt_reuse_plan(lines, plan, display_options=display_options)
            _format_dbt_non_model_sections(lines, plan, display_options=display_options)
        return
    display_argv: str = _format_display_argv(
        plan.dbt_command_argv,
        display_options=display_options,
    )
    lines.append(f"  {style.label('command')}: {style.command(display_argv)}")
    argv: tuple[str, ...]
    for argv in plan.supplemental_dbt_command_argvs:
        lines.append(
            f"  {style.label('command')}: "
            f"{style.command(_format_display_argv(argv, display_options=display_options))}"
        )
    if _is_verbose(display_options) or plan.dbt_model_plan is None:
        _format_dbt_selected_nodes(lines, plan, display_options=display_options)
    if _is_verbose(display_options) and plan.selection.dbt_required_unique_ids:
        lines.append("")
        lines.append(style.dbt_label(f"  required: {len(plan.selection.dbt_required_unique_ids)}"))
        if plan.dbt_required_selector_terms:
            lines.append(
                f"    {style.label('selectors')}: "
                f"{style.command(' '.join(plan.dbt_required_selector_terms))}"
            )
        unique_id: str
        visible_required: Sequence[str] = visible_entries(
            plan.selection.dbt_required_unique_ids, options=display_options
        )
        for unique_id in visible_required:
            lines.append(f"    {style.dbt_object_name(unique_id)}")
        append_overflow_line(
            lines,
            total_count=len(plan.selection.dbt_required_unique_ids),
            visible_count=len(visible_required),
            indent="    ",
            options=display_options,
        )
    _format_dbt_model_plan(lines, plan, display_options=display_options)
    _format_dbt_reuse_plan(lines, plan, display_options=display_options)
    _format_dbt_non_model_sections(lines, plan, display_options=display_options)


def _format_dbt_reuse_plan(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    if plan.dbt_reuse_plan is None:
        return
    entries: tuple[DbtReusePlanEntry, ...] = plan.dbt_reuse_plan.entries
    if not entries:
        return
    style: CliStyle = CliStyle(use_color=True)
    counts: Counter[DbtReusePlanAction] = Counter(entry.action for entry in entries)
    has_actionable_reuse_output: bool = any(
        counts[action] > 0
        for action in (
            DbtReusePlanAction.COMPLETE_REUSE,
            DbtReusePlanAction.SEEDED_REUSE,
            DbtReusePlanAction.BLOCKED,
            DbtReusePlanAction.SKIPPED,
        )
    )
    if not has_actionable_reuse_output and not _is_verbose(display_options):
        return
    lines.append("")
    lines.append(f"  {style.plan_section('Reuse plan')}")
    lines.append(
        "    "
        + ", ".join(
            (
                f"reuse: {counts[DbtReusePlanAction.COMPLETE_REUSE]}",
                f"baseline reuse: {counts[DbtReusePlanAction.SEEDED_REUSE]}",
                f"current: {counts[DbtReusePlanAction.CURRENT]}",
                f"rebuild: {counts[DbtReusePlanAction.REBUILD]}",
                f"blocked: {counts[DbtReusePlanAction.BLOCKED]}",
                f"skipped: {counts[DbtReusePlanAction.SKIPPED]}",
            )
        )
    )
    if not _is_verbose(display_options):
        _format_dbt_reuse_plan_action_entries(
            lines,
            entries=entries,
            action=DbtReusePlanAction.COMPLETE_REUSE,
            display_options=display_options,
        )
        _format_dbt_reuse_plan_action_entries(
            lines,
            entries=entries,
            action=DbtReusePlanAction.SEEDED_REUSE,
            display_options=display_options,
        )
        _format_dbt_reuse_plan_action_entries(
            lines,
            entries=entries,
            action=DbtReusePlanAction.BLOCKED,
            display_options=display_options,
        )
        return

    action: DbtReusePlanAction
    for action in DbtReusePlanAction:
        _format_dbt_reuse_plan_action_entries(
            lines,
            entries=entries,
            action=action,
            display_options=display_options,
        )


def _format_dbt_reuse_plan_action_entries(
    lines: list[str],
    *,
    entries: tuple[DbtReusePlanEntry, ...],
    action: DbtReusePlanAction,
    display_options: DisplayOptions,
) -> None:
    action_entries: tuple[DbtReusePlanEntry, ...] = tuple(
        entry for entry in entries if entry.action == action
    )
    if not action_entries:
        return
    style: CliStyle = CliStyle(use_color=True)
    name_column_width: int = resolve_name_column_width(tuple(entry.unique_id for entry in entries))
    section_label: str = f"{_dbt_reuse_plan_action_label(action)} ({len(action_entries)})"
    lines.append(f"    {style.plan_section(section_label)}")
    visible_action_entries: Sequence[DbtReusePlanEntry] = visible_entries(
        action_entries, options=display_options
    )
    for entry in visible_action_entries:
        lines.append(
            "      "
            + format_aligned_name_value(
                plain_name=entry.unique_id,
                styled_name=style.dbt_object_name(entry.unique_id),
                value=style.muted(_dbt_reuse_plan_reason_label(entry.reason)),
                name_column_width=name_column_width,
            )
        )
    _append_dbt_overflow_line(
        lines,
        total_count=len(action_entries),
        visible_count=len(visible_action_entries),
        indent="      ",
        options=display_options,
    )


def _format_dbt_dependency_baseline_plan(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    if plan.dbt_dependency_baseline_plan is None:
        return
    entries: tuple[DbtReusePlanEntry, ...] = tuple(
        entry
        for entry in plan.dbt_dependency_baseline_plan.entries
        if entry.action in {DbtReusePlanAction.COMPLETE_REUSE, DbtReusePlanAction.SEEDED_REUSE}
    )
    if not entries:
        return
    style: CliStyle = CliStyle(use_color=True)
    counts: Counter[DbtReusePlanAction] = Counter(entry.action for entry in entries)
    lines.append("")
    lines.append(f"  {style.plan_section('Dependency baseline')}")
    lines.append(
        "    "
        + ", ".join(
            (
                f"reuse: {counts[DbtReusePlanAction.COMPLETE_REUSE]}",
                f"baseline: {counts[DbtReusePlanAction.SEEDED_REUSE]}",
            )
        )
    )
    _format_dbt_reuse_plan_action_entries(
        lines,
        entries=entries,
        action=DbtReusePlanAction.COMPLETE_REUSE,
        display_options=display_options,
    )
    _format_dbt_reuse_plan_action_entries(
        lines,
        entries=entries,
        action=DbtReusePlanAction.SEEDED_REUSE,
        display_options=display_options,
    )


def _format_dbt_model_plan(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    if plan.dbt_model_plan is None:
        return
    style: CliStyle = CliStyle(use_color=True)
    run_ids: tuple[str, ...] = plan.dbt_model_plan.displayed_run_unique_ids
    current_ids: tuple[str, ...] = plan.dbt_model_plan.displayed_current_unique_ids
    blocked_ids: tuple[str, ...] = plan.dbt_model_plan.displayed_blocked_unique_ids
    blocked_sqlbuild: tuple[str, ...] = plan.dbt_model_plan.blocked_sqlbuild_model_names
    if not run_ids and not current_ids and not blocked_ids:
        return
    displayed_entries: tuple[DbtModelPlanEntry, ...] = plan.dbt_model_plan.displayed_entries
    entries_by_action: dict[DbtModelPlanAction, tuple[DbtModelPlanEntry, ...]] = {
        action: tuple(entry for entry in displayed_entries if entry.action == action)
        for action in DbtModelPlanAction
    }
    lines.append("")
    lines.append(f"  {style.plan_section('Model plan')}")
    name_column_width: int = resolve_name_column_width(
        tuple(entry.unique_id for entry in displayed_entries)
    )
    if run_ids:
        _format_dbt_run_reason_sections(
            lines,
            entries_by_action[DbtModelPlanAction.RUN],
            style=style,
            name_column_width=name_column_width,
            display_options=display_options,
        )
    lines.append(f"    {style.plan_section(f'Current ({len(current_ids)})')}")
    if current_ids:
        visible_current: Sequence[DbtModelPlanEntry] = visible_entries(
            entries_by_action[DbtModelPlanAction.CURRENT], options=display_options
        )
        for entry in visible_current:
            _append_dbt_model_plan_entry(
                lines,
                entry,
                style=style,
                name_column_width=name_column_width,
            )
        _append_dbt_overflow_line(
            lines,
            total_count=len(current_ids),
            visible_count=len(visible_current),
            indent="      ",
            options=display_options,
        )
    lines.append(f"    {style.plan_section(f'Blocked ({len(blocked_ids)})')}")
    if blocked_ids:
        visible_blocked: Sequence[DbtModelPlanEntry] = visible_entries(
            entries_by_action[DbtModelPlanAction.BLOCKED], options=display_options
        )
        for entry in visible_blocked:
            _append_dbt_model_plan_entry(
                lines,
                entry,
                style=style,
                name_column_width=name_column_width,
            )
        _append_dbt_overflow_line(
            lines,
            total_count=len(blocked_ids),
            visible_count=len(visible_blocked),
            indent="      ",
            options=display_options,
        )
    if blocked_sqlbuild:
        lines.append(f"    {style.label('blocked SQLBuild')}: {len(blocked_sqlbuild)}")
        visible_sqlbuild: Sequence[str] = visible_entries(blocked_sqlbuild, options=display_options)
        for name in visible_sqlbuild:
            lines.append(f"      {style.object_name(name)}")
        _append_dbt_overflow_line(
            lines,
            total_count=len(blocked_sqlbuild),
            visible_count=len(visible_sqlbuild),
            indent="      ",
            options=display_options,
        )


def _format_dbt_run_reason_sections(
    lines: list[str],
    run_entries: tuple[DbtModelPlanEntry, ...],
    *,
    style: CliStyle,
    name_column_width: int,
    display_options: DisplayOptions,
) -> None:
    reason_order: tuple[DbtModelPlanReason, ...] = (
        DbtModelPlanReason.CHECKSUM_CHANGED,
        DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED,
        DbtModelPlanReason.UPSTREAM_CHANGED,
        DbtModelPlanReason.RELATION_MISSING,
        DbtModelPlanReason.FIRST_RUN,
        DbtModelPlanReason.FULL_REFRESH,
        DbtModelPlanReason.SOURCE_FRESHNESS_ERROR,
    )
    reason: DbtModelPlanReason
    for reason in reason_order:
        reason_entries: tuple[DbtModelPlanEntry, ...] = tuple(
            entry for entry in run_entries if entry.reason == reason
        )
        if not reason_entries:
            continue
        reason_label: str = _dbt_model_plan_reason_section_label(reason)
        lines.append(f"    {style.plan_section(f'{reason_label} ({len(reason_entries)})')}")
        visible_entries_for_reason: Sequence[DbtModelPlanEntry] = visible_entries(
            reason_entries, options=display_options
        )
        for entry in visible_entries_for_reason:
            _append_dbt_model_plan_entry(
                lines,
                entry,
                style=style,
                name_column_width=name_column_width,
            )
        _append_dbt_overflow_line(
            lines,
            total_count=len(reason_entries),
            visible_count=len(visible_entries_for_reason),
            indent="      ",
            options=display_options,
        )


def _format_dbt_resource_summary(lines: list[str], plan: DbtInteropPlan) -> None:
    if plan.dbt_model_plan is None:
        return
    selected_resource_count: int = len(plan.dbt_selected_unique_ids)
    required_resource_count: int = len(plan.selection.dbt_required_unique_ids)
    planned_model_count: int = len(plan.dbt_model_plan.displayed_entries)
    non_model_count: int = len(plan.dbt_non_model_run_unique_ids)
    if not selected_resource_count and not planned_model_count and not non_model_count:
        return
    style: CliStyle = CliStyle(use_color=True)
    resource_counts: Counter[str] = Counter(
        _dbt_resource_type_display_label(node.resource_type) for node in plan.dbt_selected_nodes
    )
    selected_breakdown: str = _format_count_breakdown(resource_counts)
    run_count: int = len(plan.dbt_model_plan.displayed_run_unique_ids)
    current_count: int = len(plan.dbt_model_plan.displayed_current_unique_ids)
    blocked_count: int = len(plan.dbt_model_plan.displayed_blocked_unique_ids)
    lines.append(
        style.muted(
            "  selected by dbt selector: "
            f"{selected_resource_count} from dbt selector"
            + (f" ({selected_breakdown})" if selected_breakdown else "")
        )
    )
    if required_resource_count:
        required_names: str = ", ".join(plan.selection.dbt_required_unique_ids)
        lines.append(
            style.muted(
                f"  added for SQLBuild dependencies: {required_resource_count} dbt resources"
                + (f" ({required_names})" if required_names else "")
            )
        )
    lines.append(
        style.muted(
            f"  planned models: {run_count} run, {current_count} current, {blocked_count} blocked"
        )
    )
    lines.append(
        style.muted(
            f"  planned non-model dbt work: {non_model_count}"
            + (" selected tests/seeds preserved for execution" if non_model_count else "")
        )
    )


def _format_plan_ready_resource_counts(
    *, dbt_selected_count: int, dbt_required_count: int, sqlbuild_count: int, total_count: int
) -> str:
    if dbt_required_count:
        parts: list[str] = []
        if dbt_selected_count:
            parts.append(f"{dbt_selected_count} selected dbt")
        parts.append(f"{dbt_required_count} required dbt")
        if sqlbuild_count:
            parts.append(f"{sqlbuild_count} SQLBuild")
        return ", ".join(parts)
    return f"{total_count} selected resources"


def _format_dbt_section_resource_counts(*, selected_count: int, required_count: int) -> str:
    if required_count:
        if selected_count:
            return f"{selected_count} selected, {required_count} required"
        return f"{required_count} required"
    return f"{selected_count} selected resources"


def _format_count_breakdown(resource_counts: Counter[str]) -> str:
    if not resource_counts:
        return ""
    ordered_labels: tuple[str, ...] = ("model", "seed", "test", "unit test")
    parts: list[str] = []
    for label in ordered_labels:
        count: int = resource_counts.get(label, 0)
        if count:
            parts.append(f"{count} {_pluralize(label, count)}")
    for label, count in sorted(resource_counts.items()):
        if label not in ordered_labels and count:
            parts.append(f"{count} {_pluralize(label, count)}")
    return ", ".join(parts)


def _pluralize(label: str, count: int) -> str:
    if count == 1:
        return label
    if label == "unit test":
        return "unit tests"
    return f"{label}s"


def _append_dbt_model_plan_entry(
    lines: list[str], entry: DbtModelPlanEntry, *, style: CliStyle, name_column_width: int
) -> None:
    lines.append(
        "    "
        + format_aligned_name_value(
            plain_name=entry.unique_id,
            styled_name=style.dbt_object_name(entry.unique_id),
            value=style.muted(_dbt_model_plan_reason_label(entry.reason)),
            name_column_width=name_column_width,
        )
    )
    _append_dbt_query_diff(lines, entry, style=style)


def _append_dbt_query_diff(lines: list[str], entry: DbtModelPlanEntry, *, style: CliStyle) -> None:
    if entry.reason != DbtModelPlanReason.CHECKSUM_CHANGED:
        return
    if entry.previous_query_sql is None or entry.fingerprint_query_sql is None:
        return
    if entry.previous_query_sql == entry.fingerprint_query_sql:
        return
    lines.append(style.label("      query diff:"))
    lines.extend(format_query_diff(entry.previous_query_sql, entry.fingerprint_query_sql))


def _dbt_model_plan_reason_label(reason: DbtModelPlanReason) -> str:
    labels: dict[DbtModelPlanReason, str] = {
        DbtModelPlanReason.FIRST_RUN: "first run",
        DbtModelPlanReason.FULL_REFRESH: "full refresh",
        DbtModelPlanReason.RELATION_MISSING: "relation missing",
        DbtModelPlanReason.CHECKSUM_CHANGED: "checksum changed",
        DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED: "source freshness changed",
        DbtModelPlanReason.UPSTREAM_CHANGED: "upstream changed",
        DbtModelPlanReason.NO_CHANGE: "no change",
        DbtModelPlanReason.SOURCE_FRESHNESS_ERROR: "source freshness error",
    }
    return labels[reason]


def _dbt_model_plan_reason_section_label(reason: DbtModelPlanReason) -> str:
    labels: dict[DbtModelPlanReason, str] = {
        DbtModelPlanReason.FIRST_RUN: "First run",
        DbtModelPlanReason.FULL_REFRESH: "Full refresh",
        DbtModelPlanReason.RELATION_MISSING: "Relation missing",
        DbtModelPlanReason.CHECKSUM_CHANGED: "Checksum changed",
        DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED: "Source freshness changed",
        DbtModelPlanReason.UPSTREAM_CHANGED: "Upstream changed",
        DbtModelPlanReason.NO_CHANGE: "Current",
        DbtModelPlanReason.SOURCE_FRESHNESS_ERROR: "Source freshness error",
    }
    return labels[reason]


def _dbt_reuse_plan_action_label(action: DbtReusePlanAction) -> str:
    if action == DbtReusePlanAction.COMPLETE_REUSE:
        return "Reuse"
    if action == DbtReusePlanAction.SEEDED_REUSE:
        return "Baseline reuse"
    return action.value.replace("_", " ").title()


def _dbt_reuse_plan_reason_label(reason: DbtReusePlanReason) -> str:
    labels: dict[DbtReusePlanReason, str] = {
        DbtReusePlanReason.DESTINATION_CURRENT: "destination current",
        DbtReusePlanReason.DESTINATION_MISSING: "destination missing",
        DbtReusePlanReason.FINGERPRINT_MISSING: "fingerprint missing",
        DbtReusePlanReason.FINGERPRINT_CHANGED: "fingerprint changed",
        DbtReusePlanReason.FULL_REFRESH: "full refresh",
        DbtReusePlanReason.SOURCE_FRESHNESS_BLOCK: "source freshness block",
        DbtReusePlanReason.NON_PHYSICAL_RESOURCE: "non-physical resource",
        DbtReusePlanReason.MANIFEST_NODE_MISSING: "manifest node missing",
        DbtReusePlanReason.REUSE_METADATA_INVALID: "reuse metadata invalid",
        DbtReusePlanReason.ORIGIN_RELATION_MISSING: "production relation missing",
        DbtReusePlanReason.DEFINITION_CHANGED: "definition changed",
    }
    return labels[reason]


def _dbt_skip_reason_label(reason: DbtInteropSkipReason) -> str:
    if reason == DbtInteropSkipReason.DBT_MODELS_CURRENT:
        return "all planned dbt models are current"
    return "no dbt work selected"


def _format_dbt_non_model_sections(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    run_ids: frozenset[str] = frozenset(plan.dbt_non_model_run_unique_ids)
    pruned_seed_ids: frozenset[str] = frozenset(plan.dbt_pruned_seed_unique_ids)
    pruned_test_ids: frozenset[str] = frozenset(plan.dbt_pruned_test_unique_ids)
    seed_nodes: tuple[DbtLsNode, ...] = _nodes_by_unique_ids(
        nodes=plan.dbt_selected_nodes,
        unique_ids=run_ids,
        resource_type=DbtSupportedResourceType.SEED,
    )
    test_nodes: tuple[DbtLsNode, ...] = _nodes_by_unique_ids(
        nodes=plan.dbt_selected_nodes,
        unique_ids=run_ids,
        resource_type=DbtSupportedResourceType.TEST,
    )
    unit_test_nodes: tuple[DbtLsNode, ...] = _nodes_by_unique_ids(
        nodes=plan.dbt_selected_nodes,
        unique_ids=run_ids,
        resource_type=DbtSupportedResourceType.UNIT_TEST,
    )
    if seed_nodes or test_nodes or unit_test_nodes:
        style: CliStyle = CliStyle(use_color=True)
        lines.append("")
        lines.append(f"  {style.plan_section('Non-model dbt work')}")
        if seed_nodes:
            _format_dbt_non_model_resource_group(
                lines,
                label=f"Seeds ({len(seed_nodes)}, always run)",
                nodes=seed_nodes,
                display_options=display_options,
            )
        if test_nodes:
            _format_dbt_non_model_resource_group(
                lines,
                label=f"Tests ({len(test_nodes)})",
                nodes=test_nodes,
                display_options=display_options,
            )
        if unit_test_nodes:
            _format_dbt_non_model_resource_group(
                lines,
                label=f"Unit tests ({len(unit_test_nodes)})",
                nodes=unit_test_nodes,
                display_options=display_options,
            )
    if pruned_seed_ids:
        pruned_seed_nodes: tuple[DbtLsNode, ...] = _nodes_by_unique_ids(
            nodes=plan.dbt_selected_nodes,
            unique_ids=pruned_seed_ids,
            resource_type=DbtSupportedResourceType.SEED,
        )
        _format_dbt_pruned_non_model_group(
            lines,
            label=f"Seeds pruned ({len(pruned_seed_nodes)})",
            note="pruned because all planned dbt models are current",
            nodes=pruned_seed_nodes,
            display_options=display_options,
        )
    if pruned_test_ids:
        pruned_nodes: tuple[DbtLsNode, ...] = _nodes_by_unique_ids(
            nodes=plan.dbt_selected_nodes,
            unique_ids=pruned_test_ids,
            resource_type=DbtSupportedResourceType.TEST,
        )
        _format_dbt_pruned_non_model_group(
            lines,
            label=f"Tests pruned ({len(pruned_nodes)})",
            note="use sqb dbt test to run dbt validation",
            nodes=pruned_nodes,
            display_options=display_options,
        )
        pruned_unit_test_nodes: tuple[DbtLsNode, ...] = _nodes_by_unique_ids(
            nodes=plan.dbt_selected_nodes,
            unique_ids=pruned_test_ids,
            resource_type=DbtSupportedResourceType.UNIT_TEST,
        )
        _format_dbt_pruned_non_model_group(
            lines,
            label=f"Unit tests pruned ({len(pruned_unit_test_nodes)})",
            note="use sqb dbt test to run dbt validation",
            nodes=pruned_unit_test_nodes,
            display_options=display_options,
        )


def _format_dbt_non_model_resource_group(
    lines: list[str], *, label: str, nodes: tuple[DbtLsNode, ...], display_options: DisplayOptions
) -> None:
    style: CliStyle = CliStyle(use_color=True)
    lines.append(f"    {style.plan_section(label)}")
    visible_nodes: Sequence[DbtLsNode] = visible_entries(nodes, options=display_options)
    node: DbtLsNode
    for node in visible_nodes:
        lines.append(f"      {style.dbt_object_name(_dbt_node_display_name(node))}")
    _append_dbt_overflow_line(
        lines,
        total_count=len(nodes),
        visible_count=len(visible_nodes),
        indent="      ",
        options=display_options,
    )


def _format_dbt_pruned_non_model_group(
    lines: list[str],
    *,
    label: str,
    note: str,
    nodes: tuple[DbtLsNode, ...],
    display_options: DisplayOptions,
) -> None:
    if not nodes:
        return
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(f"  {style.plan_section(label)}")
    lines.append(style.muted(f"    {note}"))
    visible_nodes: Sequence[DbtLsNode] = visible_entries(nodes, options=display_options)
    node: DbtLsNode
    for node in visible_nodes:
        lines.append(f"    {style.muted(_dbt_node_display_name(node))}")
    _append_dbt_overflow_line(
        lines,
        total_count=len(nodes),
        visible_count=len(visible_nodes),
        indent="    ",
        options=display_options,
    )


def _nodes_by_unique_ids(
    *,
    nodes: tuple[DbtLsNode, ...],
    unique_ids: frozenset[str],
    resource_type: DbtSupportedResourceType,
) -> tuple[DbtLsNode, ...]:
    return tuple(
        sorted(
            (
                node
                for node in nodes
                if node.unique_id in unique_ids and node.resource_type == resource_type
            ),
            key=_dbt_node_sort_key,
        )
    )


def _format_dbt_model_plan_json(plan: DbtInteropPlan) -> dict[str, object] | None:
    if plan.dbt_model_plan is None:
        return None
    return {
        "run_unique_ids": list(plan.dbt_model_plan.run_unique_ids),
        "current_unique_ids": list(plan.dbt_model_plan.current_unique_ids),
        "blocked_unique_ids": list(plan.dbt_model_plan.blocked_unique_ids),
        "stale_sqlbuild_model_names": list(plan.dbt_model_plan.stale_sqlbuild_model_names),
        "blocked_sqlbuild_model_names": list(plan.dbt_model_plan.blocked_sqlbuild_model_names),
        "entries": [
            {
                "unique_id": entry.unique_id,
                "action": entry.action.value,
                "reason": entry.reason.value,
                "previous_version_hash": entry.previous_version_hash,
                "expected_version_hash": entry.expected_version_hash,
                "blocked_source_unique_ids": list(entry.blocked_source_unique_ids),
            }
            for entry in plan.dbt_model_plan.entries
        ],
    }


def _format_dbt_reuse_plan_json(plan: DbtInteropPlan) -> dict[str, object] | None:
    if plan.dbt_reuse_plan is None:
        return None
    entries: tuple[DbtReusePlanEntry, ...] = plan.dbt_reuse_plan.entries
    return {
        "complete_reuse_unique_ids": list(plan.dbt_reuse_plan.complete_reuse_unique_ids),
        "seeded_reuse_unique_ids": list(plan.dbt_reuse_plan.seeded_reuse_unique_ids),
        "rebuild_unique_ids": list(plan.dbt_reuse_plan.rebuild_unique_ids),
        "entries": [
            {
                "unique_id": entry.unique_id,
                "action": entry.action.value,
                "reason": entry.reason.value,
                "materialization": entry.materialization,
                "destination_relation_name": entry.destination_relation_name,
                "origin_relation_name": entry.origin_relation_name,
                "dbt_plan_action": entry.dbt_plan_action.value
                if entry.dbt_plan_action is not None
                else None,
                "dbt_plan_reason": entry.dbt_plan_reason.value
                if entry.dbt_plan_reason is not None
                else None,
                "skip_reason": entry.skip_reason.value if entry.skip_reason is not None else None,
            }
            for entry in entries
        ],
    }


def _format_dbt_dependency_baseline_plan_json(
    plan: DbtInteropPlan,
) -> dict[str, object] | None:
    if plan.dbt_dependency_baseline_plan is None:
        return None
    entries: tuple[DbtReusePlanEntry, ...] = plan.dbt_dependency_baseline_plan.entries
    return {
        "complete_reuse_unique_ids": list(
            plan.dbt_dependency_baseline_plan.complete_reuse_unique_ids
        ),
        "seeded_reuse_unique_ids": list(plan.dbt_dependency_baseline_plan.seeded_reuse_unique_ids),
        "entries": [
            {
                "unique_id": entry.unique_id,
                "action": entry.action.value,
                "reason": entry.reason.value,
                "materialization": entry.materialization,
                "destination_relation_name": entry.destination_relation_name,
                "origin_relation_name": entry.origin_relation_name,
                "dbt_plan_action": entry.dbt_plan_action.value
                if entry.dbt_plan_action is not None
                else None,
                "dbt_plan_reason": entry.dbt_plan_reason.value
                if entry.dbt_plan_reason is not None
                else None,
                "skip_reason": entry.skip_reason.value if entry.skip_reason is not None else None,
            }
            for entry in entries
        ],
    }


def _format_dbt_selected_nodes(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    if not plan.dbt_selected_nodes:
        return
    nodes_by_type: dict[str, list[DbtLsNode]] = defaultdict(list)
    node: DbtLsNode
    for node in sorted(plan.dbt_selected_nodes, key=_dbt_node_sort_key):
        nodes_by_type[_dbt_resource_type_label(node.resource_type)].append(node)
    section_label: str
    nodes: list[DbtLsNode]
    style: CliStyle = CliStyle(use_color=True)
    for section_label, nodes in sorted(nodes_by_type.items()):
        lines.append("")
        lines.append(f"  {style.plan_section(f'{section_label} ({len(nodes)})')}")
        labels: tuple[str, ...] = tuple(_dbt_node_display_name(node) for node in nodes)
        name_width: int = resolve_name_column_width(labels)
        visible_nodes: Sequence[DbtLsNode] = visible_entries(nodes, options=display_options)
        for node in visible_nodes:
            name: str = _dbt_node_display_name(node)
            lines.append(
                "    "
                + format_aligned_name_value(
                    plain_name=name,
                    styled_name=style.dbt_object_name(name),
                    value=node.resource_type or "resource",
                    name_column_width=name_width,
                )
            )
        _append_dbt_overflow_line(
            lines,
            total_count=len(nodes),
            visible_count=len(visible_nodes),
            indent="    ",
            options=display_options,
        )


def _format_display_argv(argv: tuple[str, ...], *, display_options: DisplayOptions) -> str:
    if _is_verbose(display_options):
        return " ".join(argv)
    max_terms: int | None = display_options.max_entries_per_section
    if max_terms is None or "--select" not in argv:
        return " ".join(argv)
    display: list[str] = []
    index: int = 0
    while index < len(argv):
        token: str = argv[index]
        display.append(token)
        index += 1
        if token != "--select":
            continue
        select_terms: list[str] = []
        while index < len(argv) and not argv[index].startswith("--"):
            select_terms.append(argv[index])
            index += 1
        display.extend(select_terms[:max_terms])
        hidden_count: int = len(select_terms) - max_terms
        if hidden_count > 0:
            display.append(f"... and {hidden_count} more")
    return " ".join(display)


def _append_dbt_overflow_line(
    lines: list[str], *, total_count: int, visible_count: int, indent: str, options: DisplayOptions
) -> None:
    before_count: int = len(lines)
    append_overflow_line(
        lines,
        total_count=total_count,
        visible_count=visible_count,
        indent=indent,
        options=options,
    )
    if len(lines) > before_count:
        style: CliStyle = CliStyle(use_color=True)
        lines[-1] = style.muted(lines[-1])


def _format_sqlbuild_section(
    lines: list[str],
    plan: DbtInteropPlan,
    *,
    use_color: bool,
    display_options: DisplayOptions,
) -> None:
    style: CliStyle = CliStyle(use_color=True)
    sqlbuild_count: int = len(plan.selection.sqlbuild_model_names)
    lines.append(style.object_name(f"SQLBuild ({sqlbuild_count} selected)"))
    if plan.sqlbuild_skip_reason is not None:
        lines.append(style.muted("  skipped: no SQLBuild work selected"))
        return
    argv: tuple[str, ...]
    for argv in plan.sqlbuild_command_argvs:
        lines.append(f"  {style.label('command')}: {style.command(' '.join(argv))}")
    if plan.sqlbuild_plan_output is None:
        _format_sqlbuild_model_fallback(lines, plan, display_options=display_options)
        return
    sqlbuild_plan: str = format_plan(
        plan.sqlbuild_plan_output,
        use_color=use_color,
        include_header=False,
        display_options=display_options,
        section_header_style=style.plan_section,
    )
    if not sqlbuild_plan:
        return
    lines.append("")
    sqlbuild_lines: list[str] = sqlbuild_plan.splitlines()
    while sqlbuild_lines and not sqlbuild_lines[0]:
        sqlbuild_lines.pop(0)
    line: str
    for line in sqlbuild_lines:
        lines.append(f"  {line}" if line else "")


def _format_dbt_test_plan(
    plan: DbtInteropPlan,
    *,
    use_color: bool,
    display_options: DisplayOptions,
) -> str:
    style: CliStyle = CliStyle(use_color=True)
    dbt_model_names: tuple[str, ...] = _dbt_test_model_names(plan)
    dbt_test_node_count: int = len(_dbt_test_nodes(plan))
    sqlbuild_test_count: int = (
        len(plan.sqlbuild_plan_output.test_entries) if plan.sqlbuild_plan_output is not None else 0
    )
    sqlbuild_audit_count: int = (
        len(plan.sqlbuild_plan_output.audit_entries) if plan.sqlbuild_plan_output is not None else 0
    )
    lines: list[str] = []
    lines.append(
        style.success_strong(
            "Plan ready ("
            + _format_test_plan_ready_counts(
                dbt_model_count=len(dbt_model_names),
                sqlbuild_test_count=sqlbuild_test_count,
                sqlbuild_audit_count=sqlbuild_audit_count,
            )
            + ")"
        )
    )
    _format_dbt_test_section(
        lines,
        plan,
        dbt_model_names=dbt_model_names,
        dbt_test_node_count=dbt_test_node_count,
        display_options=display_options,
    )
    _format_sqlbuild_test_section(
        lines,
        plan,
        sqlbuild_test_count=sqlbuild_test_count,
        sqlbuild_audit_count=sqlbuild_audit_count,
        display_options=display_options,
    )
    _format_warning_section(lines, plan)
    result: str = "\n".join(lines)
    return result if use_color else _strip_ansi(result)


def _format_test_plan_ready_counts(
    *, dbt_model_count: int, sqlbuild_test_count: int, sqlbuild_audit_count: int
) -> str:
    parts: list[str] = []
    if dbt_model_count:
        parts.append(f"{dbt_model_count} dbt {_pluralize('model', dbt_model_count)}")
    if sqlbuild_test_count:
        parts.append(f"{sqlbuild_test_count} SQLBuild {_pluralize('test', sqlbuild_test_count)}")
    if sqlbuild_audit_count:
        parts.append(f"{sqlbuild_audit_count} {_pluralize('audit', sqlbuild_audit_count)}")
    if not parts:
        return "nothing selected"
    return ", ".join(parts)


def _format_dbt_test_section(
    lines: list[str],
    plan: DbtInteropPlan,
    *,
    dbt_model_names: tuple[str, ...],
    dbt_test_node_count: int,
    display_options: DisplayOptions,
) -> None:
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(
        style.dbt_section(
            f"dbt ({len(dbt_model_names)} {_pluralize('model', len(dbt_model_names))})"
        )
    )
    if not dbt_model_names:
        lines.append(style.muted("  no dbt models selected"))
        return
    visible_models: Sequence[str] = visible_entries(dbt_model_names, options=display_options)
    model_name: str
    for model_name in visible_models:
        lines.append(f"  {style.dbt_object_name(model_name)}")
    _append_dbt_overflow_line(
        lines,
        total_count=len(dbt_model_names),
        visible_count=len(visible_models),
        indent="  ",
        options=display_options,
    )
    if dbt_test_node_count:
        lines.append(style.muted(f"  dbt tests: {dbt_test_node_count}"))
    else:
        lines.append(style.muted("  dbt tests: none"))


def _format_sqlbuild_test_section(
    lines: list[str],
    plan: DbtInteropPlan,
    *,
    sqlbuild_test_count: int,
    sqlbuild_audit_count: int,
    display_options: DisplayOptions,
) -> None:
    style: CliStyle = CliStyle(use_color=True)
    if sqlbuild_test_count:
        lines.append("")
        lines.append(
            style.object_name(
                f"SQLBuild tests ({sqlbuild_test_count} {_pluralize('test', sqlbuild_test_count)})"
            )
        )
        _format_sqlbuild_test_groups(
            lines,
            plan.sqlbuild_plan_output,
            display_options=display_options,
        )
    if sqlbuild_audit_count:
        audit_label: str = _pluralize("audit", sqlbuild_audit_count)
        lines.append("")
        lines.append(style.object_name(f"SQLBuild audits ({sqlbuild_audit_count} {audit_label})"))


def _format_sqlbuild_test_groups(
    lines: list[str],
    plan_output: PlanOutput | None,
    *,
    display_options: DisplayOptions,
) -> None:
    if plan_output is None:
        return
    style: CliStyle = CliStyle(use_color=True)
    tests_by_target: dict[str, list[str]] = defaultdict(list)
    entry: object
    for entry in plan_output.test_entries:
        target_name: str = _sqlbuild_test_target_name(entry)
        tests_by_target[target_name].append(getattr(entry, "name", ""))
    target: str
    for target in tests_by_target:
        lines.append(f"  {style.object_name(target)}")
        test_name: str
        for test_name in tests_by_target[target]:
            lines.append(f"    {style.muted(test_name)}")


def _sqlbuild_test_target_name(entry: object) -> str:
    chain: object = getattr(entry, "chain", ())
    if not isinstance(chain, tuple) or not chain:
        return "(unknown)"
    expected_steps: tuple[object, ...] = tuple(
        step for step in chain if getattr(step, "expected_cte_sql", None) is not None
    )
    if expected_steps:
        return getattr(expected_steps[-1], "model_name", "(unknown)")
    return getattr(chain[-1], "model_name", "(unknown)")


def _dbt_test_model_names(plan: DbtInteropPlan) -> tuple[str, ...]:
    names: list[str] = []
    node: DbtLsNode
    for node in plan.dbt_selected_nodes:
        if node.resource_type == DbtSupportedResourceType.MODEL:
            names.append(_dbt_node_display_name(node))
    return tuple(dict.fromkeys(names))


def _dbt_test_nodes(plan: DbtInteropPlan) -> tuple[DbtLsNode, ...]:
    return tuple(
        node
        for node in plan.dbt_selected_nodes
        if node.resource_type in {DbtSupportedResourceType.TEST, DbtSupportedResourceType.UNIT_TEST}
    )


def _format_sqlbuild_model_fallback(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    style: CliStyle = CliStyle(use_color=True)
    name_width: int = resolve_name_column_width(plan.selection.sqlbuild_model_names)
    visible_models: Sequence[str] = visible_entries(
        plan.selection.sqlbuild_model_names, options=display_options
    )
    model_name: str
    for model_name in visible_models:
        lines.append(
            "  "
            + format_aligned_name_value(
                plain_name=model_name,
                styled_name=style.object_name(model_name),
                value="model",
                name_column_width=name_width,
            )
        )
    append_overflow_line(
        lines,
        total_count=len(plan.selection.sqlbuild_model_names),
        visible_count=len(visible_models),
        indent="  ",
        options=display_options,
    )


def _format_anchor_section(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    if not _is_verbose(display_options) or not plan.selection.dbt_anchor_terms:
        return
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(style.plan_section(f"dbt anchors ({len(plan.selection.dbt_anchor_terms)})"))
    term: str
    for term in plan.selection.dbt_anchor_terms:
        unique_ids: tuple[str, ...] = plan.selection.dbt_anchor_unique_ids_by_term.get(term, ())
        lines.append(f"  {style.command(term)}: {style.value(str(len(unique_ids)))}")
        unique_id: str
        visible_unique_ids: Sequence[str] = visible_entries(unique_ids, options=display_options)
        for unique_id in visible_unique_ids:
            lines.append(f"    {style.dbt_object_name(unique_id)}")
        append_overflow_line(
            lines,
            total_count=len(unique_ids),
            visible_count=len(visible_unique_ids),
            indent="    ",
            options=display_options,
        )


def _is_verbose(display_options: DisplayOptions) -> bool:
    return display_options.max_entries_per_section is None


def _format_path_translation_section(lines: list[str], plan: DbtInteropPlan) -> None:
    if not plan.selection.path_translations:
        return
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(
        style.success_strong(f"Path translations ({len(plan.selection.path_translations)})")
    )
    original: str
    translated: str
    for original, translated in plan.selection.path_translations:
        lines.append(f"  {original} -> {translated}")


def _format_warning_section(lines: list[str], plan: DbtInteropPlan) -> None:
    if not plan.warnings:
        return
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(style.warning_strong(f"Warnings ({len(plan.warnings)})"))
    warning: str
    for warning in plan.warnings:
        lines.append(f"  {style.warning(f'- {warning}')}")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_PATTERN.sub("", text)


def _dbt_node_display_name(node: DbtLsNode) -> str:
    if node.package_name and node.name:
        return f"{node.package_name}.{node.name}"
    if node.name:
        return node.name
    return node.unique_id


def _dbt_resource_type_label(resource_type: str | None) -> str:
    if resource_type is None:
        return "Resources"
    return f"{resource_type.replace('_', ' ').title()}s"


def _dbt_resource_type_display_label(resource_type: str | None) -> str:
    if resource_type is None:
        return "resource"
    return resource_type.replace("_", " ")


def _dbt_node_sort_key(node: DbtLsNode) -> tuple[str, str]:
    return (_dbt_resource_type_label(node.resource_type), _dbt_node_display_name(node))
