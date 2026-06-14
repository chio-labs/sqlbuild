"""Plan construction and formatting for dbt interop commands."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence

from sqlbuild.cli.commands.main.plan_format import format_plan
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import (
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtModelPlanningResult,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSkipReason
from sqlbuild.shared.helpers.alignment import format_aligned_name_value, resolve_name_column_width
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.display import DisplayOptions, append_overflow_line, visible_entries

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
    return DbtInteropPlan(
        command=normalized_command,
        dbt_command_argv=tuple(dbt_command_argv),
        dbt_selected_nodes=tuple(dbt_ls_nodes),
        dbt_selected_unique_ids=dbt_selected_unique_ids,
        sqlbuild_command_argvs=tuple(tuple(argv) for argv in sqlbuild_command_argvs),
        selection=selection,
        sqlbuild_plan_output=sqlbuild_plan_output,
        dbt_model_plan=dbt_model_plan,
        dbt_required_selector_terms=tuple(dbt_required_selector_terms),
        supplemental_dbt_command_argvs=tuple(
            tuple(argv) for argv in supplemental_dbt_command_argvs
        ),
        dbt_skip_reason=None if dbt_has_work else DbtInteropSkipReason.NO_DBT_WORK,
        sqlbuild_skip_reason=None if sqlbuild_has_work else DbtInteropSkipReason.NO_SQLBUILD_WORK,
        warnings=tuple(warnings),
    )


def format_dbt_interop_plan(
    plan: DbtInteropPlan,
    *,
    use_color: bool = True,
    display_options: DisplayOptions | None = None,
) -> str:
    """Format a dbt interop plan for human CLI output."""

    lines: list[str] = []
    resolved_display_options: DisplayOptions = display_options or DisplayOptions()
    selected_count: int = len(
        frozenset((*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids))
    ) + len(plan.selection.sqlbuild_model_names)
    style: CliStyle = CliStyle(use_color=True)
    lines.append(style.success_strong(f"Plan ready ({selected_count} selected)"))
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
            "skipped": plan.dbt_skip_reason is not None,
            "skip_reason": plan.dbt_skip_reason.value if plan.dbt_skip_reason is not None else None,
            "model_plan": _format_dbt_model_plan_json(plan),
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
    dbt_count: int = len(
        frozenset((*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids))
    )
    lines.append(style.dbt_section(f"dbt ({dbt_count} selected)"))
    if plan.dbt_skip_reason is not None:
        lines.append(style.muted(f"  skipped: {_dbt_skip_reason_label(plan.dbt_skip_reason)}"))
        if plan.dbt_skip_reason == DbtInteropSkipReason.DBT_MODELS_CURRENT:
            _format_dbt_model_plan(lines, plan, display_options=display_options)
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


def _format_dbt_model_plan(
    lines: list[str], plan: DbtInteropPlan, *, display_options: DisplayOptions
) -> None:
    if plan.dbt_model_plan is None:
        return
    style: CliStyle = CliStyle(use_color=True)
    run_ids: tuple[str, ...] = plan.dbt_model_plan.run_unique_ids
    current_ids: tuple[str, ...] = plan.dbt_model_plan.current_unique_ids
    blocked_ids: tuple[str, ...] = plan.dbt_model_plan.blocked_unique_ids
    blocked_sqlbuild: tuple[str, ...] = plan.dbt_model_plan.blocked_sqlbuild_model_names
    if not run_ids and not current_ids and not blocked_ids:
        return
    lines.append("")
    lines.append(f"  {style.plan_section('Model plan')}")
    lines.append(f"    {style.plan_section(f'Run ({len(run_ids)})')}")
    if run_ids:
        visible_run: Sequence[str] = visible_entries(run_ids, options=display_options)
        for unique_id in visible_run:
            lines.append(f"      {style.dbt_object_name(unique_id)}")
        _append_dbt_overflow_line(
            lines,
            total_count=len(run_ids),
            visible_count=len(visible_run),
            indent="      ",
            options=display_options,
        )
    lines.append(f"    {style.plan_section(f'Current ({len(current_ids)})')}")
    if current_ids:
        visible_current: Sequence[str] = visible_entries(current_ids, options=display_options)
        for unique_id in visible_current:
            lines.append(f"      {style.dbt_object_name(unique_id)}")
        _append_dbt_overflow_line(
            lines,
            total_count=len(current_ids),
            visible_count=len(visible_current),
            indent="      ",
            options=display_options,
        )
    lines.append(f"    {style.plan_section(f'Blocked ({len(blocked_ids)})')}")
    if blocked_ids:
        visible_blocked: Sequence[str] = visible_entries(blocked_ids, options=display_options)
        for unique_id in visible_blocked:
            lines.append(f"      {style.dbt_object_name(unique_id)}")
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


def _dbt_skip_reason_label(reason: DbtInteropSkipReason) -> str:
    if reason == DbtInteropSkipReason.DBT_MODELS_CURRENT:
        return "all planned dbt models are current"
    return "no dbt work selected"


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
        lines.append(f"  - {warning}")


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


def _dbt_node_sort_key(node: DbtLsNode) -> tuple[str, str]:
    return (_dbt_resource_type_label(node.resource_type), _dbt_node_display_name(node))
