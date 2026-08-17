"""Plan construction and formatting for ordinary dbt interop commands."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence

from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult, DbtLsNode
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSkipReason
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.append_overflow_line import append_overflow_line
from sqlbuild.presentation.main.surface_header import format_surface_header
from sqlbuild.presentation.main.tree_connector import tree_connector
from sqlbuild.presentation.main.visible_entries import visible_entries
from sqlbuild.presentation.models import DisplayOptions

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
) -> DbtInteropPlan:
    """Build a display-ready selection plan without dbt model state."""

    normalized_command: DbtInteropCommand = DbtInteropCommand(command)
    dbt_selected_unique_ids: tuple[str, ...] = tuple(
        sorted(node.unique_id for node in dbt_ls_nodes)
    )
    dbt_has_work: bool = bool(dbt_selected_unique_ids or selection.dbt_required_unique_ids)
    sqlbuild_has_work: bool = bool(selection.sqlbuild_model_names)
    resolved_warnings: tuple[str, ...] = tuple(warnings)
    no_match_warning: str = "No dbt or SQLBuild resources matched the selection."
    if not dbt_has_work and not sqlbuild_has_work and no_match_warning not in resolved_warnings:
        resolved_warnings = (*resolved_warnings, no_match_warning)
    return DbtInteropPlan(
        command=normalized_command,
        dbt_command_argv=tuple(dbt_command_argv),
        dbt_selected_nodes=tuple(dbt_ls_nodes),
        dbt_selected_unique_ids=dbt_selected_unique_ids,
        sqlbuild_command_argvs=tuple(tuple(argv) for argv in sqlbuild_command_argvs),
        selection=selection,
        sqlbuild_plan_output=sqlbuild_plan_output,
        dbt_required_selector_terms=tuple(dbt_required_selector_terms),
        supplemental_dbt_command_argvs=tuple(
            tuple(argv) for argv in supplemental_dbt_command_argvs
        ),
        dbt_skip_reason=None if dbt_has_work else DbtInteropSkipReason.NO_DBT_WORK,
        sqlbuild_skip_reason=None if sqlbuild_has_work else DbtInteropSkipReason.NO_SQLBUILD_WORK,
        warnings=resolved_warnings,
    )


def format_dbt_interop_plan(
    *,
    plan: DbtInteropPlan,
    use_color: bool = True,
    display_options: DisplayOptions | None = None,
) -> str:
    """Format selected dbt and SQLBuild work without change classifications."""

    options: DisplayOptions = display_options or DisplayOptions()
    selected_count: int = len(
        frozenset((*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids))
    ) + len(plan.selection.sqlbuild_model_names)
    style: CliStyle = CliStyle(use_color=True)
    lines: list[str] = [
        format_surface_header(
            style=style, title="Plan ready", context=f"{selected_count} selected resources"
        ),
        "",
    ]
    lines = _format_dbt_section(lines=lines, plan=plan, options=options)
    lines.append("")
    lines = _format_sqlbuild_section(lines=lines, plan=plan, options=options, use_color=use_color)
    lines = _format_anchor_section(lines=lines, plan=plan, options=options)
    lines = _format_path_translation_section(lines=lines, plan=plan)
    lines = _format_warning_section(lines=lines, plan=plan)
    result: str = "\n".join(lines)
    return result if use_color else _ANSI_ESCAPE_PATTERN.sub("", result)


def format_dbt_interop_plan_json(plan: DbtInteropPlan) -> str:
    """Serialize an ordinary interop selection plan to stable JSON."""

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
        },
        "sqlbuild": {
            "argvs": [list(argv) for argv in plan.sqlbuild_command_argvs],
            "selected_models": list(plan.selection.sqlbuild_model_names),
            "skipped": plan.sqlbuild_skip_reason is not None,
            "skip_reason": (
                plan.sqlbuild_skip_reason.value if plan.sqlbuild_skip_reason is not None else None
            ),
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
    *, lines: list[str], plan: DbtInteropPlan, options: DisplayOptions
) -> list[str]:
    style: CliStyle = CliStyle(use_color=True)
    selected_count: int = len(plan.dbt_selected_unique_ids)
    required_count: int = len(plan.selection.dbt_required_unique_ids)
    lines.append(
        f"{style.dbt_label('dbt')} "
        f"{style.dbt_section(f'({selected_count} selected, {required_count} required)')}"
    )
    if plan.dbt_skip_reason is not None:
        lines.append(style.muted("  skipped: no dbt work selected"))
        return lines
    lines.append(f"  {style.label('command')}: {style.command(' '.join(plan.dbt_command_argv))}")
    nodes_by_type: dict[str, list[DbtLsNode]] = defaultdict(list)
    for node in sorted(plan.dbt_selected_nodes, key=_dbt_node_sort_key):
        nodes_by_type[node.resource_type or "resource"].append(node)
    for resource_type, nodes in sorted(nodes_by_type.items()):
        lines.append("")
        lines.append(f"  {style.plan_section(f'{resource_type} ({len(nodes)})')}")
        visible_nodes: Sequence[DbtLsNode] = visible_entries(entries=nodes, options=options)
        node_index: int
        for node_index, node in enumerate(visible_nodes):
            connector: str = tree_connector(
                style=style,
                last=node_index == len(visible_nodes) - 1 and len(nodes) <= len(visible_nodes),
            )
            lines.append(f"  {connector} {style.dbt_object_name(_dbt_node_display_name(node))}")
        lines = append_overflow_line(
            lines=lines,
            total_count=len(nodes),
            visible_count=len(visible_nodes),
            indent="    ",
            options=options,
        )
    if required_count:
        lines.append("")
        lines.append(style.dbt_label(f"  required ({required_count})"))
        required_ids: Sequence[str] = visible_entries(
            entries=plan.selection.dbt_required_unique_ids,
            options=options,
        )
        unique_id_index: int
        for unique_id_index, unique_id in enumerate(required_ids):
            connector = tree_connector(style=style, last=unique_id_index == len(required_ids) - 1)
            lines.append(f"  {connector} {style.dbt_object_name(unique_id)}")
    return lines


def _format_sqlbuild_section(
    *,
    lines: list[str],
    plan: DbtInteropPlan,
    options: DisplayOptions,
    use_color: bool,
) -> list[str]:
    style: CliStyle = CliStyle(use_color=True)
    lines.append(style.plan_section(f"SQLBuild ({len(plan.selection.sqlbuild_model_names)})"))
    if plan.sqlbuild_skip_reason is not None:
        lines.append(style.muted("  skipped: no SQLBuild work selected"))
        return lines
    if plan.sqlbuild_plan_output is not None:
        rendered: str = format_plan(
            plan=plan.sqlbuild_plan_output,
            use_color=use_color,
            display_options=options,
        )
        lines.extend(f"  {line}" if line else "" for line in rendered.splitlines())
        return lines
    for name in visible_entries(entries=plan.selection.sqlbuild_model_names, options=options):
        lines.append(f"  {style.object_name(name)}")
    return lines


def _format_anchor_section(
    *, lines: list[str], plan: DbtInteropPlan, options: DisplayOptions
) -> list[str]:
    if not plan.selection.dbt_anchor_terms:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.extend(("", style.label("dbt selector anchors")))
    visible_terms: Sequence[str] = visible_entries(
        entries=plan.selection.dbt_anchor_terms,
        options=options,
    )
    for term in visible_terms:
        count: int = len(plan.selection.dbt_anchor_unique_ids_by_term.get(term, ()))
        lines.append(f"  {style.command(term)}: {count} dbt resources")
    return lines


def _format_path_translation_section(*, lines: list[str], plan: DbtInteropPlan) -> list[str]:
    if not plan.selection.path_translations:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.extend(("", style.label("path translations")))
    for original, translated in plan.selection.path_translations:
        lines.append(f"  {style.command(original)} -> {style.command(translated)}")
    return lines


def _format_warning_section(*, lines: list[str], plan: DbtInteropPlan) -> list[str]:
    if not plan.warnings:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.extend(("", style.warning("Warnings")))
    for warning in plan.warnings:
        lines.append(style.warning(f"  {warning}"))
    return lines


def _dbt_node_display_name(node: DbtLsNode) -> str:
    if node.fqn:
        return ".".join(node.fqn)
    return node.name or node.unique_id


def _dbt_node_sort_key(node: DbtLsNode) -> tuple[str, str]:
    return node.resource_type or "", _dbt_node_display_name(node)
