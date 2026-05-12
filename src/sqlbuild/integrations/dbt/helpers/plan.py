"""Plan construction and formatting for dbt interop commands."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult, DbtLsNode
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSkipReason
from sqlbuild.shared.helpers.alignment import format_aligned_name_value, resolve_name_column_width
from sqlbuild.shared.helpers.colors import blue_bold, green_bold, yellow_bold

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
) -> DbtInteropPlan:
    """Build a display-ready plan from dbt preflight and SQLBuild selection results."""

    normalized_command: DbtInteropCommand = DbtInteropCommand(command)
    dbt_selected_unique_ids: tuple[str, ...] = tuple(
        sorted(node.unique_id for node in dbt_ls_nodes)
    )
    sqlbuild_model_names: tuple[str, ...] = selection.sqlbuild_model_names
    dbt_has_work: bool = bool(dbt_selected_unique_ids or selection.dbt_required_unique_ids)
    sqlbuild_has_work: bool = bool(sqlbuild_model_names)
    return DbtInteropPlan(
        command=normalized_command,
        dbt_command_argv=tuple(dbt_command_argv),
        dbt_selected_unique_ids=dbt_selected_unique_ids,
        sqlbuild_command_argvs=tuple(tuple(argv) for argv in sqlbuild_command_argvs),
        selection=selection,
        dbt_required_selector_terms=tuple(dbt_required_selector_terms),
        supplemental_dbt_command_argvs=tuple(
            tuple(argv) for argv in supplemental_dbt_command_argvs
        ),
        dbt_skip_reason=None if dbt_has_work else DbtInteropSkipReason.NO_DBT_WORK,
        sqlbuild_skip_reason=None if sqlbuild_has_work else DbtInteropSkipReason.NO_SQLBUILD_WORK,
        warnings=tuple(warnings),
    )


def format_dbt_interop_plan(plan: DbtInteropPlan, *, use_color: bool = True) -> str:
    """Format a dbt interop plan for human CLI output."""

    lines: list[str] = []
    selected_count: int = len(
        frozenset((*plan.dbt_selected_unique_ids, *plan.selection.dbt_required_unique_ids))
    ) + len(plan.selection.sqlbuild_model_names)
    lines.append(green_bold(f"Plan ready ({selected_count} selected)"))
    lines.append("")
    _format_dbt_section(lines, plan)
    lines.append("")
    _format_sqlbuild_section(lines, plan)
    _format_anchor_section(lines, plan)
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


def _format_dbt_section(lines: list[str], plan: DbtInteropPlan) -> None:
    lines.append(green_bold("dbt"))
    if plan.dbt_skip_reason is not None:
        lines.append("  skipped: no dbt work selected")
        return
    lines.append(f"  command: {' '.join(plan.dbt_command_argv)}")
    argv: tuple[str, ...]
    for argv in plan.supplemental_dbt_command_argvs:
        lines.append(f"  command: {' '.join(argv)}")
    if plan.dbt_selected_unique_ids:
        lines.append(f"  selected: {len(plan.dbt_selected_unique_ids)}")
    if plan.selection.dbt_required_unique_ids:
        lines.append(f"  required: {len(plan.selection.dbt_required_unique_ids)}")
        if plan.dbt_required_selector_terms:
            lines.append(f"    selectors: {' '.join(plan.dbt_required_selector_terms)}")
        unique_id: str
        for unique_id in plan.selection.dbt_required_unique_ids:
            lines.append(f"    {unique_id}")


def _format_sqlbuild_section(lines: list[str], plan: DbtInteropPlan) -> None:
    lines.append(green_bold("SQLBuild"))
    if plan.sqlbuild_skip_reason is not None:
        lines.append("  skipped: no SQLBuild work selected")
        return
    argv: tuple[str, ...]
    for argv in plan.sqlbuild_command_argvs:
        lines.append(f"  command: {' '.join(argv)}")
    name_width: int = resolve_name_column_width(plan.selection.sqlbuild_model_names)
    model_name: str
    for model_name in plan.selection.sqlbuild_model_names:
        lines.append(
            "  "
            + format_aligned_name_value(
                plain_name=model_name,
                styled_name=blue_bold(model_name),
                value="model",
                name_column_width=name_width,
            )
        )


def _format_anchor_section(lines: list[str], plan: DbtInteropPlan) -> None:
    if not plan.selection.dbt_anchor_terms:
        return
    lines.append("")
    lines.append(green_bold(f"dbt anchors ({len(plan.selection.dbt_anchor_terms)})"))
    term: str
    for term in plan.selection.dbt_anchor_terms:
        unique_ids: tuple[str, ...] = plan.selection.dbt_anchor_unique_ids_by_term.get(term, ())
        lines.append(f"  {term}: {len(unique_ids)}")
        unique_id: str
        for unique_id in unique_ids:
            lines.append(f"    {unique_id}")


def _format_path_translation_section(lines: list[str], plan: DbtInteropPlan) -> None:
    if not plan.selection.path_translations:
        return
    lines.append("")
    lines.append(green_bold(f"Path translations ({len(plan.selection.path_translations)})"))
    original: str
    translated: str
    for original, translated in plan.selection.path_translations:
        lines.append(f"  {original} -> {translated}")


def _format_warning_section(lines: list[str], plan: DbtInteropPlan) -> None:
    if not plan.warnings:
        return
    lines.append("")
    lines.append(yellow_bold(f"Warnings ({len(plan.warnings)})"))
    warning: str
    for warning in plan.warnings:
        lines.append(f"  - {warning}")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_PATTERN.sub("", text)
