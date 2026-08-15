"""Plan output formatting grouped by reason with inline detail."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from typing import cast

from sqlbuild.cli.output._helpers.cursor_plan import build_cursor_plan_details
from sqlbuild.cli.output.models import CursorPlanDetails
from sqlbuild.cli.output.types import CursorBoundsOwner, CursorResolutionStatus
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.main.changes.query_diff import format_query_diff
from sqlbuild.compiler.planner.main.execution.cursor_bound_display import cursor_bound_display
from sqlbuild.compiler.planner.main.execution.inclusive_cursor_end import inclusive_cursor_end
from sqlbuild.compiler.planner.main.execution.model_materialization_label import (
    model_materialization_label,
)
from sqlbuild.compiler.planner.models import (
    CascadeResult,
    CursorBounds,
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    PlanProviderUsage,
    PlanWarning,
    RunDespiteUnchangedDecision,
    SchemaFinding,
    SourceLoadPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    IncrementalMode,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    WarningSeverity,
)
from sqlbuild.compiler.python_nodes.types import PythonIdentityStatus, PythonRunPhase
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.aligned_name_value import format_aligned_name_value
from sqlbuild.presentation.main.append_overflow_line import append_overflow_line
from sqlbuild.presentation.main.resolve_name_column_width import resolve_name_column_width
from sqlbuild.presentation.main.visible_entries import visible_entries
from sqlbuild.presentation.models import DisplayOptions
from sqlbuild.runtime.contracts.types import ExecutionResourceKind

_DIFF_HEADER_MARKER: str = "# "
_STALE_INPUT_WARNING_TITLE: str = "Stale inputs detected"

_REASON_GROUP_ORDER: tuple[PlanReason, ...] = (
    PlanReason.QUERY_CHANGED,
    PlanReason.CONFIG_CHANGED,
    PlanReason.SCHEMA_CHANGED,
    PlanReason.RUN_DESPITE_UNCHANGED,
    PlanReason.FIRST_RUN,
)

_REASON_GROUP_LABELS: dict[PlanReason, str] = {
    PlanReason.QUERY_CHANGED: "Query changed",
    PlanReason.CONFIG_CHANGED: "Config changed",
    PlanReason.SCHEMA_CHANGED: "Schema changed",
    PlanReason.RUN_DESPITE_UNCHANGED: "Runs despite unchanged",
    PlanReason.FIRST_RUN: "First run",
}

_ANSI_ESCAPE_PATTERN: re.Pattern[str] = re.compile(r"\033\[[0-9;]*m")
_SCHEMA_CHANGE_SYMBOLS: dict[SchemaChangeKind, str] = {
    SchemaChangeKind.COLUMN_ADDED: "+",
    SchemaChangeKind.COLUMN_REMOVED: "-",
    SchemaChangeKind.COLUMN_TYPE_CHANGED: "~",
}


def format_plan(
    *,
    plan: PlanOutput,
    full_refresh: bool = False,
    use_color: bool = True,
    include_header: bool = True,
    display_options: DisplayOptions | None = None,
    section_header_style: Callable[[str], str] | None = None,
    python_plan_entries: tuple[PythonPlanEntry, ...] = (),
    include_standard_freshness_diagnostics: bool = True,
) -> str:
    """Format plan output grouped by reason with inline detail."""

    lines: list[str] = []

    resolved_display_options: DisplayOptions = display_options or DisplayOptions()
    style: CliStyle = CliStyle(use_color=True)
    resolved_section_header_style: Callable[[str], str] = section_header_style or style.plan_section

    if full_refresh:
        lines = _format_full_refresh(
            lines=lines,
            plan=plan,
            include_header=include_header,
            display_options=resolved_display_options,
            section_header_style=resolved_section_header_style,
            python_plan_entries=python_plan_entries,
        )
        lines = _format_warnings(
            lines=lines,
            plan=plan,
            include_standard_freshness_diagnostics=(include_standard_freshness_diagnostics),
        )
        result: str = "\n".join(lines)
        return result if use_color else _strip_ansi(result)

    active: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]
    selected_count: int = _selected_count(plan)
    name_column_width: int = _resolve_name_column_width(
        plan=plan, python_plan_entries=python_plan_entries
    )

    if include_header:
        header: str = _plan_ready_header(
            selected_count=selected_count,
            source_load_entries=plan.source_load_entries,
            python_plan_entries=python_plan_entries,
            full_refresh=False,
        )
        lines.append(style.success_strong(header))

    lines = _format_virtual_metadata(
        lines=lines,
        plan=plan,
        section_header_style=resolved_section_header_style,
        display_options=resolved_display_options,
    )
    if include_standard_freshness_diagnostics:
        lines = _format_standard_source_freshness_metadata(
            lines=lines,
            plan=plan,
            section_header_style=resolved_section_header_style,
            display_options=resolved_display_options,
        )
    lines = _format_standard_remaining_stale_metadata(
        lines=lines,
        plan=plan,
        section_header_style=resolved_section_header_style,
        display_options=resolved_display_options,
    )
    lines = _format_provider_usages(
        lines=lines,
        plan=plan,
        python_plan_entries=python_plan_entries,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )
    lines = _format_standard_pruned_metadata(
        lines=lines,
        plan=plan,
        display_options=resolved_display_options,
        skipped_header_style=style.muted,
    )

    lines = _format_python_plan_entries(
        lines=lines,
        entries=_python_plan_entries_for_phase(
            entries=python_plan_entries, phase=PythonRunPhase.PRE_SQL_INGRESS
        ),
        label="Python ingress",
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )

    _format_source_loads(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )

    _format_dependency_baseline_entries(
        lines=lines,
        entries=plan.dependency_baseline_entries,
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )
    lines = _format_existing_destination_input_entries(
        lines=lines,
        entries=plan.existing_destination_input_entries,
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )

    normal: list[ModelPlanEntry] = _collect_normal(active)
    cascade: list[ModelPlanEntry] = _collect_upstream_changed(active)
    groups: dict[PlanReason, list[ModelPlanEntry]] = _group_by_reason(
        entries=active, cascade_entries=cascade
    )

    lines = _format_changed_functions(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )

    reason: PlanReason
    for reason in _REASON_GROUP_ORDER:
        entries: list[ModelPlanEntry] | None = groups.get(reason)
        if not entries:
            continue
        label: str = _REASON_GROUP_LABELS[reason]
        lines.append("")
        lines.append(resolved_section_header_style(f"{label} ({len(entries)})"))
        entry: ModelPlanEntry
        visible: Sequence[ModelPlanEntry] = visible_entries(
            entries=entries, options=resolved_display_options
        )
        for entry in visible:
            lines = _format_detail_entry(
                lines=lines, entry=entry, reason=reason, name_column_width=name_column_width
            )
        lines = append_overflow_line(
            lines=lines,
            total_count=len(entries),
            visible_count=len(visible),
            indent="  ",
            options=resolved_display_options,
        )

    if cascade:
        lines.append("")
        lines.append(resolved_section_header_style(f"Upstream changed ({len(cascade)})"))
        entry_c: ModelPlanEntry
        visible_cascade: Sequence[ModelPlanEntry] = visible_entries(
            entries=cascade, options=resolved_display_options
        )
        for entry_c in visible_cascade:
            lines = _format_upstream_changed_entry(
                lines=lines, entry=entry_c, name_column_width=name_column_width
            )
        lines = append_overflow_line(
            lines=lines,
            total_count=len(cascade),
            visible_count=len(visible_cascade),
            indent="  ",
            options=resolved_display_options,
        )

    if normal:
        lines.append("")
        lines = _format_routine_models_section(
            lines=lines,
            entries=normal,
            name_column_width=name_column_width,
            display_options=resolved_display_options,
            section_header_style=resolved_section_header_style,
        )

    lines = _format_routine_functions(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )

    lines = _format_seeds(
        lines=lines,
        plan=plan,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )

    lines = _format_python_plan_entries(
        lines=lines,
        entries=_python_plan_entries_for_phase(
            entries=python_plan_entries, phase=PythonRunPhase.READ_SIDE
        ),
        label="Python read-side",
        name_column_width=name_column_width,
        display_options=resolved_display_options,
        section_header_style=resolved_section_header_style,
    )
    lines = _format_warnings(
        lines=lines,
        plan=plan,
        include_standard_freshness_diagnostics=include_standard_freshness_diagnostics,
    )

    output: str = "\n".join(lines)
    return output if use_color else _strip_ansi(output)


def _format_full_refresh(
    *,
    lines: list[str],
    plan: PlanOutput,
    include_header: bool,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
    python_plan_entries: tuple[PythonPlanEntry, ...],
) -> list[str]:
    """Format the full refresh variant of plan output."""

    selected_count: int = _selected_count(plan)
    active: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]
    name_column_width: int = _resolve_name_column_width(
        plan=plan, python_plan_entries=python_plan_entries
    )

    if include_header:
        lines.append(
            CliStyle(use_color=True).success_strong(
                _plan_ready_header(
                    selected_count=selected_count,
                    source_load_entries=plan.source_load_entries,
                    python_plan_entries=python_plan_entries,
                    full_refresh=True,
                )
            )
        )

    lines = _format_provider_usages(
        lines=lines,
        plan=plan,
        python_plan_entries=python_plan_entries,
        display_options=display_options,
        section_header_style=section_header_style,
    )

    lines = _format_python_plan_entries(
        lines=lines,
        entries=_python_plan_entries_for_phase(
            entries=python_plan_entries, phase=PythonRunPhase.PRE_SQL_INGRESS
        ),
        label="Python ingress",
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )

    _format_source_loads(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )

    _format_functions(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )
    if lines:
        lines.append("")

    counts: Counter[str] = Counter()
    entry: ModelPlanEntry
    for entry in active:
        label: str = model_materialization_label(entry)
        counts[label] += 1

    lines.append(section_header_style(f"Full refresh ({len(active)})"))
    count_label: str
    count_value: int
    for count_label, count_value in counts.most_common():
        lines.append(f"  {count_value:>3} {count_label}")

    lines = _format_seeds(
        lines=lines,
        plan=plan,
        display_options=display_options,
        section_header_style=section_header_style,
    )

    lines = _format_python_plan_entries(
        lines=lines,
        entries=_python_plan_entries_for_phase(
            entries=python_plan_entries, phase=PythonRunPhase.READ_SIDE
        ),
        label="Python read-side",
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )
    return lines


def _selected_count(plan: PlanOutput) -> int:
    """Count selected executable resources shown in plan output."""

    return len(plan.model_entries) + len(plan.seed_entries) + len(plan.function_entries)


def _format_dependency_baseline_entries(
    *,
    lines: list[str],
    entries: tuple[DependencyBaselinePlanEntry, ...],
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> None:
    if not entries:
        return
    lines = _format_reuse_input_entries(
        lines=lines,
        entries=entries,
        label="Reused inputs",
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )


def _format_reuse_input_entries(
    *,
    lines: list[str],
    entries: tuple[DependencyBaselinePlanEntry, ...],
    label: str,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    if not entries:
        return lines
    lines.append("")
    lines.append(section_header_style(f"{label} ({len(entries)})"))
    visible: Sequence[DependencyBaselinePlanEntry] = visible_entries(
        entries=entries, options=display_options
    )
    entry: DependencyBaselinePlanEntry
    for entry in visible:
        lines.append(
            "  "
            + _format_name_value_line(
                name=entry.name,
                value=_reuse_input_detail(entry),
                name_column_width=name_column_width,
            )
        )
    lines = append_overflow_line(
        lines=lines,
        total_count=len(entries),
        visible_count=len(visible),
        indent="  ",
        options=display_options,
    )
    return lines


def _reuse_input_detail(entry: DependencyBaselinePlanEntry) -> str:
    copy_kind: str = "hard-copy" if entry.relation_reuse.hard_copy else "cheap clone"
    return f"{entry.resource_label}  {copy_kind} from reuse origin target"


def _format_existing_destination_input_entries(
    *,
    lines: list[str],
    entries: tuple[ExistingDestinationInputPlanEntry, ...],
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    if not entries:
        return lines
    lines.append("")
    lines.append(section_header_style(f"Existing destination inputs ({len(entries)})"))
    visible: Sequence[ExistingDestinationInputPlanEntry] = visible_entries(
        entries=entries, options=display_options
    )
    entry: ExistingDestinationInputPlanEntry
    for entry in visible:
        lines.append(
            "  "
            + _format_name_value_line(
                name=entry.name,
                value=_existing_destination_input_detail(entry),
                name_column_width=name_column_width,
            )
        )
    lines = append_overflow_line(
        lines=lines,
        total_count=len(entries),
        visible_count=len(visible),
        indent="  ",
        options=display_options,
    )
    return lines


def _existing_destination_input_detail(entry: ExistingDestinationInputPlanEntry) -> str:
    return f"{entry.status} in destination target"


def _plan_ready_header(
    *,
    selected_count: int,
    source_load_entries: tuple[SourceLoadPlanEntry, ...],
    python_plan_entries: tuple[PythonPlanEntry, ...],
    full_refresh: bool,
) -> str:
    source_count: int = len(source_load_entries)
    parts: list[str] = []
    if full_refresh:
        parts.append("full refresh")
    parts.append(f"{selected_count} selected")
    if source_count:
        source_noun: str = "source" if source_count == 1 else "sources"
        action: str = "reload" if any(e.is_reload for e in source_load_entries) else "load"
        source_label: str = f"{source_noun} to {action}"
        parts.append(f"{source_count} {source_label}")
    python_count: int = len(python_plan_entries)
    if python_count:
        node_noun: str = "node" if python_count == 1 else "nodes"
        parts.append(f"{python_count} Python {node_noun}")
    return f"Plan ready ({', '.join(parts)})"


def _python_plan_entries_for_phase(
    *, entries: tuple[PythonPlanEntry, ...], phase: PythonRunPhase
) -> tuple[PythonPlanEntry, ...]:
    return tuple(entry for entry in entries if entry.phase == phase)


def _format_provider_usages(
    *,
    lines: list[str],
    plan: PlanOutput,
    python_plan_entries: tuple[PythonPlanEntry, ...],
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    usages: tuple[PlanProviderUsage, ...] = _all_provider_usages(
        plan=plan,
        python_plan_entries=python_plan_entries,
    )
    if not usages:
        return lines
    usage_by_provider: dict[str, list[PlanProviderUsage]] = {}
    usage: PlanProviderUsage
    for usage in usages:
        usage_by_provider.setdefault(usage.provider_name, []).append(usage)
    lines.append("")
    lines.append(section_header_style("Providers"))
    verbose: bool = display_options.max_entries_per_section is None
    provider_names: list[str] = sorted(usage_by_provider)
    style: CliStyle = CliStyle(use_color=True)
    if not verbose:
        provider_width: int = max(len(name) for name in provider_names)
        for provider_name in provider_names:
            count: int = len(usage_by_provider[provider_name])
            surface_word: str = "surface" if count == 1 else "surfaces"
            padding: str = " " * max(0, provider_width - len(provider_name))
            lines.append(
                f"  {style.object_name(provider_name)}{padding}  "
                f"{style.muted(f'used by {count} selected Python {surface_word}')}"
            )
        return lines
    for provider_name in provider_names:
        lines.append(f"  {style.object_name(provider_name)}")
        provider_usages: list[PlanProviderUsage] = sorted(
            usage_by_provider[provider_name],
            key=lambda item: (item.consumer_kind, item.consumer_name, item.parameter_name),
        )
        visible: Sequence[PlanProviderUsage] = visible_entries(
            entries=provider_usages,
            options=display_options,
        )
        for usage in visible:
            annotation: str = (
                f" ({usage.annotation_class_name})"
                if usage.annotation_class_name is not None
                else ""
            )
            lines.append(
                f"    {style.muted(usage.consumer_kind)} "
                f"{style.object_name(usage.consumer_name)}{annotation}"
            )
        lines = append_overflow_line(
            lines=lines,
            total_count=len(provider_usages),
            visible_count=len(visible),
            indent="    ",
            options=display_options,
        )
    return lines


def _all_provider_usages(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...]
) -> tuple[PlanProviderUsage, ...]:
    usages: list[PlanProviderUsage] = list(plan.provider_usages)
    python_entry: PythonPlanEntry
    for python_entry in python_plan_entries:
        usages.extend(
            PlanProviderUsage(
                provider_name=provider_usage.provider_name,
                consumer_kind=python_entry.kind.value,
                consumer_name=python_entry.name,
                parameter_name=provider_usage.parameter_name,
                annotation_class_name=provider_usage.annotation_class_name,
                annotation_module=provider_usage.annotation_module,
            )
            for provider_usage in python_entry.provider_usages
        )
    return tuple(usages)


def _format_standard_pruned_metadata(
    *,
    lines: list[str],
    plan: PlanOutput,
    display_options: DisplayOptions,
    skipped_header_style: Callable[[str], str],
) -> list[str]:
    raw_names: object = plan.metadata.get("standard_pruned_model_names")
    if not isinstance(raw_names, tuple):
        return lines
    names: tuple[str, ...] = tuple(name for name in raw_names if isinstance(name, str))
    if not names:
        return lines
    lines.append("")
    lines.append(skipped_header_style(f"Skipped current models ({len(names)} already up to date)"))
    if display_options.max_entries_per_section is not None:
        return lines
    visible_names: Sequence[str] = visible_entries(entries=names, options=display_options)
    name: str
    name_column_width: int = resolve_name_column_width(names=names)
    for name in visible_names:
        lines.append(
            _format_name_value_line(
                name=name, value="up to date", name_column_width=name_column_width
            )
        )
    lines = append_overflow_line(
        lines=lines,
        total_count=len(names),
        visible_count=len(visible_names),
        indent="  ",
        options=display_options,
    )
    return lines


def _format_python_plan_entries(
    *,
    lines: list[str],
    entries: tuple[PythonPlanEntry, ...],
    label: str,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    if not entries:
        return lines
    lines.append("")
    lines.append(section_header_style(f"{label} ({len(entries)})"))
    visible: Sequence[PythonPlanEntry] = visible_entries(entries=entries, options=display_options)
    entry: PythonPlanEntry
    for entry in visible:
        lines.append(
            _format_name_value_line(
                name=entry.name,
                value=f"{entry.kind.value} ({entry.identity_status.value})",
                name_column_width=name_column_width,
            )
        )
        lines = _append_python_identity_diff(lines=lines, entry=entry)
    lines = append_overflow_line(
        lines=lines,
        total_count=len(entries),
        visible_count=len(visible),
        indent="  ",
        options=display_options,
    )
    return lines


def _append_python_identity_diff(*, lines: list[str], entry: PythonPlanEntry) -> list[str]:
    if entry.identity_status != PythonIdentityStatus.CHANGED:
        return lines

    source_diff: list[str] = _format_python_source_diff(entry)
    dependency_diff: list[str] = _format_python_dependency_diff(entry)
    if not source_diff and not dependency_diff:
        return lines

    style: CliStyle = CliStyle(use_color=True)
    lines.append(style.label("    python diff:"))
    if source_diff:
        lines.append(style.label("      source diff:"))
        lines.extend(source_diff)
    if dependency_diff:
        lines.append(style.label("      dependency diff:"))
        lines.extend(dependency_diff)
    return lines


def _format_python_source_diff(entry: PythonPlanEntry) -> list[str]:
    previous: str | None = _python_definition_source_text(entry.previous_definition_json)
    current: str | None = _python_definition_source_text(entry.current_definition_json)
    if previous is None or current is None or previous == current:
        return []
    return _indent_diff(
        lines=format_query_diff(previous=previous, current=current), extra_indent="  "
    )


def _format_python_dependency_diff(entry: PythonPlanEntry) -> list[str]:
    previous: str | None = _python_dependency_source_text(entry.previous_metadata_json)
    current: str | None = _python_dependency_source_text(entry.current_metadata_json)
    if previous is None or current is None or previous == current:
        return []
    return _dim_python_dependency_headers(
        _indent_diff(lines=format_query_diff(previous=previous, current=current), extra_indent="  ")
    )


def _dim_python_dependency_headers(lines: list[str]) -> list[str]:
    style: CliStyle = CliStyle(use_color=True)
    result: list[str] = []
    line: str
    for line in lines:
        if _DIFF_HEADER_MARKER in _strip_ansi(line):
            result.append(style.muted(line))
        else:
            result.append(line)
    return result


def _python_definition_source_text(raw_json: str | None) -> str | None:
    payload: dict[str, object] | None = _json_object(raw_json)
    if payload is None:
        return None
    source_text: object = payload.get("source_text")
    return source_text if isinstance(source_text, str) else None


def _python_dependency_source_text(raw_json: str | None) -> str | None:
    payload: dict[str, object] | None = _json_object(raw_json)
    if payload is None:
        return None
    raw_dependencies: object = payload.get("dependencies")
    if not isinstance(raw_dependencies, list):
        return None

    dependency_blocks: list[str] = []
    dependency: object
    for dependency in sorted(raw_dependencies, key=_python_dependency_sort_key):
        if not isinstance(dependency, dict):
            continue
        dependency_payload: dict[object, object] = cast(dict[object, object], dependency)
        source_text: object = dependency_payload.get("source_text")
        if not isinstance(source_text, str):
            continue
        source_path: object = dependency_payload.get("source_path")
        module: object = dependency_payload.get("module")
        qualname: object = dependency_payload.get("qualname")
        header_parts: list[str] = []
        if isinstance(source_path, str) and source_path:
            header_parts.append(source_path)
        if isinstance(module, str) and module:
            header_parts.append(module)
        if isinstance(qualname, str) and qualname:
            header_parts.append(qualname)
        header: str = " :: ".join(header_parts) if header_parts else "dependency"
        dependency_blocks.append(f"# {header}\n{source_text}")
    return "\n\n".join(dependency_blocks)


def _python_dependency_sort_key(dependency: object) -> tuple[str, str, str]:
    if not isinstance(dependency, dict):
        return ("", "", "")
    dependency_payload: dict[object, object] = cast(dict[object, object], dependency)
    source_path: object = dependency_payload.get("source_path")
    module: object = dependency_payload.get("module")
    qualname: object = dependency_payload.get("qualname")
    return (
        source_path if isinstance(source_path, str) else "",
        module if isinstance(module, str) else "",
        qualname if isinstance(qualname, str) else "",
    )


def _json_object(raw_json: str | None) -> dict[str, object] | None:
    if raw_json is None:
        return None
    try:
        payload: object = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], payload) if isinstance(payload, dict) else None


def _indent_diff(*, lines: list[str], extra_indent: str) -> list[str]:
    return [f"{extra_indent}{line}" for line in lines]


def _format_source_loads(
    *,
    lines: list[str],
    plan: PlanOutput,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> None:
    """Append the managed source loaders section."""

    if not plan.source_load_entries:
        return
    loader_entries: tuple[SourceLoadPlanEntry, ...] = tuple(
        entry
        for entry in plan.source_load_entries
        if entry.resource_kind == ExecutionResourceKind.LOADER
    )
    source_entries: tuple[SourceLoadPlanEntry, ...] = tuple(
        entry
        for entry in plan.source_load_entries
        if entry.resource_kind == ExecutionResourceKind.SOURCE
    )
    lines = _format_load_entry_group(
        lines=lines,
        entries=loader_entries,
        label="Loaders",
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )
    lines = _format_load_entry_group(
        lines=lines,
        entries=source_entries,
        label="Sources",
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )


def _format_load_entry_group(
    *,
    lines: list[str],
    entries: tuple[SourceLoadPlanEntry, ...],
    label: str,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    if not entries:
        return lines
    action: str = "reload" if any(entry.is_reload for entry in entries) else "load"
    lines.append("")
    lines.append(section_header_style(f"{label} to {action} ({len(entries)})"))
    visible: Sequence[SourceLoadPlanEntry] = visible_entries(
        entries=entries, options=display_options
    )
    source_load_entry: SourceLoadPlanEntry
    for source_load_entry in visible:
        lines.append(
            _format_name_value_line(
                name=source_load_entry.name,
                value=_source_load_label(source_load_entry),
                name_column_width=name_column_width,
            )
        )
    lines = append_overflow_line(
        lines=lines,
        total_count=len(entries),
        visible_count=len(visible),
        indent="  ",
        options=display_options,
    )
    return lines


def _source_load_label(entry: SourceLoadPlanEntry) -> str:
    strategy: str = _source_load_strategy_label(entry)
    details: list[str] = []
    if entry.cursor_column is not None:
        details.append(f"cursor: {entry.cursor_column}")
    if entry.unique_key:
        key_text: str = ", ".join(entry.unique_key)
        details.append(f"unique_key: {key_text}")
    if not details:
        return strategy
    return f"{strategy} ({'; '.join(details)})"


def _source_load_strategy_label(entry: SourceLoadPlanEntry) -> str:
    if entry.integration_kind is not None:
        return f"external ({entry.integration_kind})"
    if entry.write_strategy is not None:
        return entry.write_strategy.value
    return "self-managed"


def _collect_normal(entries: list[ModelPlanEntry]) -> list[ModelPlanEntry]:
    """Collect entries that belong in the Normal aggregate section."""

    result: list[ModelPlanEntry] = []
    entry: ModelPlanEntry
    for entry in entries:
        if entry.reason not in (PlanReason.NO_CHANGE, PlanReason.NORMAL_INCREMENTAL):
            continue
        if entry.cascade is not None:
            continue
        result.append(entry)
    return result


def _collect_upstream_changed(entries: list[ModelPlanEntry]) -> list[ModelPlanEntry]:
    """Collect entries where cascade upgraded the effective window beyond own backfill."""

    result: list[ModelPlanEntry] = []
    entry: ModelPlanEntry
    for entry in entries:
        if entry.cascade is None:
            continue
        result.append(entry)
    return result


def _group_by_reason(
    *,
    entries: list[ModelPlanEntry],
    cascade_entries: list[ModelPlanEntry],
) -> dict[PlanReason, list[ModelPlanEntry]]:
    """Group entries by reason, excluding normal/no-change and cascade entries."""

    cascade_names: frozenset[str] = frozenset(e.name for e in cascade_entries)
    groups: dict[PlanReason, list[ModelPlanEntry]] = {}
    entry: ModelPlanEntry
    for entry in entries:
        if entry.reason in (PlanReason.NO_CHANGE, PlanReason.NORMAL_INCREMENTAL):
            continue
        if entry.name in cascade_names:
            continue
        groups.setdefault(entry.reason, []).append(entry)
    return groups


def _format_routine_models_section(
    *,
    lines: list[str],
    entries: list[ModelPlanEntry],
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    """Format routine model work by resource name."""

    lines.append(section_header_style(f"Models ({len(entries)} standard run)"))
    visible: Sequence[ModelPlanEntry] = visible_entries(entries=entries, options=display_options)
    entry: ModelPlanEntry
    for entry in visible:
        lines.append(
            _format_name_value_line(
                name=entry.name,
                value=model_materialization_label(entry),
                name_column_width=name_column_width,
            )
        )
        lines = _append_cursor_detail(lines=lines, entry=entry)
    lines = append_overflow_line(
        lines=lines,
        total_count=len(entries),
        visible_count=len(visible),
        indent="  ",
        options=display_options,
    )
    return lines


def _format_detail_entry(
    *,
    lines: list[str],
    entry: ModelPlanEntry,
    reason: PlanReason,
    name_column_width: int,
) -> list[str]:
    """Format a per-model entry with action text and detail lines."""

    if reason == PlanReason.FIRST_RUN:
        mat_label: str = model_materialization_label(entry)
        lines.append(
            _format_name_value_line(
                name=entry.name, value=mat_label, name_column_width=name_column_width
            )
        )
        lines = _append_cursor_detail(lines=lines, entry=entry)
        return lines

    action_text: str = _action_text(entry)
    lines.append(
        _format_name_value_line(
            name=entry.name, value=action_text, name_column_width=name_column_width
        )
    )
    lines = _append_cursor_detail(
        lines=lines,
        entry=entry,
        show_range=entry.backfill.action != BackfillAction.FULL,
    )
    lines = _append_policy_line(lines=lines, entry=entry)
    lines = _append_run_despite_unchanged_detail(lines=lines, entry=entry)
    lines = _append_schema_diff(lines=lines, entry=entry)
    lines = _append_config_diff(lines=lines, entry=entry)
    lines = _append_query_diff(lines=lines, entry=entry)
    return lines


def _format_upstream_changed_entry(
    *, lines: list[str], entry: ModelPlanEntry, name_column_width: int
) -> list[str]:
    """Format a per-model entry in the Upstream changed group."""

    cascade: CascadeResult | None = entry.cascade
    action_text: str = _cascade_action_text(cascade)
    lines.append(
        _format_name_value_line(
            name=entry.name, value=action_text, name_column_width=name_column_width
        )
    )
    lines = _append_cursor_detail(
        lines=lines,
        entry=entry,
        show_range=cascade is None or cascade.effective_action != BackfillAction.FULL,
    )
    if cascade is not None and cascade.root_cause is not None:
        cause_desc: str = _cascade_cause_description(cascade)
        lines.append(f"    cause: {cause_desc}")
    return lines


def _append_cursor_detail(
    *, lines: list[str], entry: ModelPlanEntry, show_range: bool = True
) -> list[str]:
    """Append cursor column, mode, and range detail lines."""

    details: CursorPlanDetails | None = build_cursor_plan_details(entry=entry)
    if details is None:
        return lines
    cursor_value: str = entry.cursor_column or ""
    if entry.cursor_type is not None:
        cursor_value = f"{cursor_value} ({entry.cursor_type})"
    lines.append(f"    cursor: {cursor_value}")
    if entry.incremental_mode == IncrementalMode.MICROBATCH:
        lines.append(f"    mode: {IncrementalMode.MICROBATCH.value}")
    if details.requested_start is not None or details.requested_end is not None:
        requested_start: str = details.requested_start or "earliest available"
        requested_end: str = details.requested_end or "latest available"
        lines.append(f"    requested: {requested_start} -> {requested_end}")
    if show_range and details.resolved_bounds is not None:
        lines.append(
            f"    range: {_format_cursor_range(bounds=details.resolved_bounds, entry=entry)}"
        )
    if entry.incremental_mode == IncrementalMode.MICROBATCH:
        lines = _append_microbatch_plan_detail(lines=lines, details=details)
    if details.bounds_owner == CursorBoundsOwner.RUNTIME:
        lines.append("    bounds: runtime-owned (model-backed cursor input)")
    elif details.resolution_status == CursorResolutionStatus.RESOLVED:
        lines.append("    bounds: planner-resolved")
    return lines


def _append_microbatch_plan_detail(*, lines: list[str], details: CursorPlanDetails) -> list[str]:
    """Append grain, batch size, and known-or-deferred batch count."""

    if details.declared_grain is not None:
        grain_text: str = details.declared_grain
        if details.effective_grain != details.declared_grain:
            grain_text = f"{details.declared_grain} -> {details.effective_grain} (effective)"
        lines.append(f"    grain: {grain_text}")
    if details.declared_batch_size is not None:
        batch_size_text: str = details.declared_batch_size
        if details.effective_batch_size != details.declared_batch_size:
            batch_size_text = (
                f"{details.declared_batch_size} -> "
                f"{details.effective_batch_size} (coarsened by upstream grain)"
            )
        lines.append(f"    batch size: {batch_size_text}")
    if details.planned_batch_count is not None and details.effective_batch_size is not None:
        lines.append(f"    batches: {details.planned_batch_count} x {details.effective_batch_size}")
    elif details.resolution_status == CursorResolutionStatus.DEFERRED:
        lines.append("    batches: resolved at runtime after upstream models complete")
    return lines


def _format_cursor_range(*, bounds: CursorBounds, entry: ModelPlanEntry) -> str:
    """Render a cursor range with an inclusive end bound."""

    start: str = cursor_bound_display(
        value=bounds.start,
        cursor_type=entry.cursor_type,
        cursor_grain=entry.cursor_grain,
    )
    inclusive_end: str = inclusive_cursor_end(
        end=bounds.end,
        cursor_type=entry.cursor_type,
        cursor_grain=entry.cursor_grain,
    )
    return f"{start} \u2192 {inclusive_end}"


def _append_policy_line(*, lines: list[str], entry: ModelPlanEntry) -> list[str]:
    """Append the policy line if a backfill policy triggered."""

    if entry.backfill.action == BackfillAction.FORWARD_ONLY:
        return lines
    duration: str = entry.backfill.duration or "full"
    policy_value: str = _backfill_value(action=entry.backfill.action, duration=duration)
    if entry.reason in (PlanReason.QUERY_CHANGED, PlanReason.SCHEMA_CHANGED):
        lines.append(f"    policy: replay_on_change={policy_value}")
    return lines


def _append_schema_diff(*, lines: list[str], entry: ModelPlanEntry) -> list[str]:
    """Append schema diff lines if findings exist."""

    if not entry.schema_findings:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.append(style.label("    schema diff:"))
    lines.extend(_format_schema_findings(entry.schema_findings))
    return lines


def _append_query_diff(*, lines: list[str], entry: ModelPlanEntry) -> list[str]:
    """Append query diff lines if previous SQL is available."""

    if entry.previous_query_sql is None:
        return lines
    if entry.reason != PlanReason.QUERY_CHANGED:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.append(style.label("    query diff:"))
    lines.extend(
        format_query_diff(previous=entry.previous_query_sql, current=entry.fingerprint_query_sql)
    )
    return lines


def _append_config_diff(*, lines: list[str], entry: ModelPlanEntry) -> list[str]:
    """Append version-identity config diff lines if metadata changed."""

    if entry.reason != PlanReason.CONFIG_CHANGED:
        return lines
    if entry.previous_metadata_json is None or entry.fingerprint_metadata_json is None:
        return lines
    previous_config: str = _format_config_json(entry.previous_metadata_json)
    current_config: str = _format_config_json(entry.fingerprint_metadata_json)
    if previous_config == current_config:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.append(style.label("    config diff:"))
    lines.extend(format_query_diff(previous=previous_config, current=current_config))
    return lines


def _format_config_json(metadata_json: str) -> str:
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return metadata_json
    config: object = payload.get("config", {}) if isinstance(payload, dict) else {}
    return json.dumps(config, sort_keys=True, indent=2, default=str)


def _action_text(entry: ModelPlanEntry) -> str:
    """Human-readable action text for inline display."""

    if entry.backfill.action == BackfillAction.BOUNDED and entry.backfill.duration is not None:
        base: str = f"rebuild last {entry.backfill.duration}"
        suffix: str = _schema_change_suffix(entry)
        return f"{base}, {suffix}" if suffix else base
    if entry.backfill.action == BackfillAction.FULL and entry.reason != PlanReason.FIRST_RUN:
        suffix = _schema_change_suffix(entry)
        return f"full rebuild, {suffix}" if suffix else "full rebuild"
    return ""


def _cascade_action_text(cascade: CascadeResult | None) -> str:
    """Action text for an upstream-changed entry."""

    if cascade is None:
        return ""
    if cascade.effective_action == BackfillAction.FULL:
        return "full rebuild"
    if (
        cascade.effective_action == BackfillAction.BOUNDED
        and cascade.effective_duration is not None
    ):
        return f"rebuild last {cascade.effective_duration}"
    return ""


def _cascade_cause_description(cascade: CascadeResult) -> str:
    """Format the cause line content for an upstream-changed entry."""

    root: str = cascade.root_cause or "unknown"
    if cascade.root_reason == PlanReason.RUN_DESPITE_UNCHANGED:
        return f"{root} ran despite unchanged inputs"
    if cascade.root_reason is not None:
        reason_text: str = _plan_reason_text(cascade.root_reason)
        if reason_text:
            return f"{root} ({reason_text})"
    if cascade.effective_action == BackfillAction.FULL:
        return f"{root} (full)"
    if (
        cascade.effective_action == BackfillAction.BOUNDED
        and cascade.effective_duration is not None
    ):
        return f"{root} ({cascade.effective_duration})"
    return root


def _plan_reason_text(reason: PlanReason) -> str:
    """Format a plan reason for cascade cause output."""

    if reason == PlanReason.QUERY_CHANGED:
        return "query changed"
    if reason == PlanReason.FUNCTION_CHANGED:
        return "function changed"
    if reason == PlanReason.CONFIG_CHANGED:
        return "config changed"
    if reason == PlanReason.SCHEMA_CHANGED:
        return "schema changed"
    if reason == PlanReason.FIRST_RUN:
        return "first run"
    if reason == PlanReason.FULL_REFRESH:
        return "full refresh"
    if reason == PlanReason.RUN_DESPITE_UNCHANGED:
        return "ran despite unchanged inputs"
    return ""


def _append_run_despite_unchanged_detail(*, lines: list[str], entry: ModelPlanEntry) -> list[str]:
    decision: RunDespiteUnchangedDecision | None = entry.run_despite_unchanged
    if decision is None:
        return lines
    detail: str = decision.duration or decision.mode.value
    lines.append(f"    run_despite_unchanged: {detail}")
    if decision.newest_source_data_age_seconds is not None:
        lines.append(
            "    newest source data age: "
            f"{_format_age_seconds(decision.newest_source_data_age_seconds)}"
        )
    return lines


def _format_age_seconds(age_seconds: int) -> str:
    if age_seconds % 86400 == 0:
        return f"{age_seconds // 86400}d"
    if age_seconds % 3600 == 0:
        return f"{age_seconds // 3600}h"
    if age_seconds % 60 == 0:
        return f"{age_seconds // 60}m"
    return f"{age_seconds}s"


def _schema_change_suffix(entry: ModelPlanEntry) -> str:
    """Short suffix describing schema changes for inline display."""

    if not entry.schema_findings:
        return ""
    kinds: set[SchemaChangeKind] = {f.kind for f in entry.schema_findings}
    parts: list[str] = []
    if SchemaChangeKind.COLUMN_ADDED in kinds:
        parts.append("add column")
    if SchemaChangeKind.COLUMN_REMOVED in kinds:
        parts.append("drop column")
    if SchemaChangeKind.COLUMN_TYPE_CHANGED in kinds:
        parts.append("type change")
    return ", ".join(parts)


def _backfill_value(*, action: BackfillAction, duration: str) -> str:
    """Format a backfill action as a policy value string."""

    if action == BackfillAction.BOUNDED:
        return f"bounded-{duration}"
    return str(action)


def _format_seeds(
    *,
    lines: list[str],
    plan: PlanOutput,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    """Append the seeds section."""

    if not plan.seed_entries:
        return lines
    lines.append("")
    lines.append(section_header_style(f"Seeds ({len(plan.seed_entries)})"))
    seed_entry: object
    visible: Sequence[object] = visible_entries(entries=plan.seed_entries, options=display_options)
    for seed_entry in visible:
        reason: object | None = getattr(seed_entry, "reason", None)
        reason_label: str = _seed_reason_label(reason)
        suffix: str = f"  ({reason_label})" if reason_label else ""
        lines.append(f"  {getattr(seed_entry, 'name', str(seed_entry))}{suffix}")
    lines = append_overflow_line(
        lines=lines,
        total_count=len(plan.seed_entries),
        visible_count=len(visible),
        indent="  ",
        options=display_options,
    )
    return lines


def _seed_reason_label(reason: object | None) -> str:
    if reason == PlanReason.FIRST_RUN:
        return "first_run"
    if reason == PlanReason.CONFIG_CHANGED:
        return "seed_changed"
    if reason == PlanReason.NO_CHANGE:
        return "current"
    return ""


def _format_functions(
    *,
    lines: list[str],
    plan: PlanOutput,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> None:
    """Append the functions section."""

    lines = _format_changed_functions(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )
    lines = _format_routine_functions(
        lines=lines,
        plan=plan,
        name_column_width=name_column_width,
        display_options=display_options,
        section_header_style=section_header_style,
    )


def _format_changed_functions(
    *,
    lines: list[str],
    plan: PlanOutput,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    """Append changed functions with details."""

    if not plan.function_entries:
        return lines
    changed_entries: list[FunctionPlanEntry] = [
        entry for entry in plan.function_entries if entry.reason != PlanReason.NO_CHANGE
    ]
    if not changed_entries:
        return lines
    lines.append("")
    lines.append(section_header_style(f"Changed functions ({len(changed_entries)})"))
    function_entry: FunctionPlanEntry
    visible_changed: Sequence[FunctionPlanEntry] = visible_entries(
        entries=changed_entries, options=display_options
    )
    for function_entry in visible_changed:
        lines = _format_function_entry(
            lines=lines,
            function_entry=function_entry,
            show_details=True,
            name_column_width=name_column_width,
        )
    lines = append_overflow_line(
        lines=lines,
        total_count=len(changed_entries),
        visible_count=len(visible_changed),
        indent="  ",
        options=display_options,
    )
    return lines


def _format_routine_functions(
    *,
    lines: list[str],
    plan: PlanOutput,
    name_column_width: int,
    display_options: DisplayOptions,
    section_header_style: Callable[[str], str],
) -> list[str]:
    """Append routine functions by resource name."""

    if not plan.function_entries:
        return lines
    unchanged_entries: list[FunctionPlanEntry] = [
        entry for entry in plan.function_entries if entry.reason == PlanReason.NO_CHANGE
    ]
    if not unchanged_entries:
        return lines
    lines.append("")
    lines.append(section_header_style(f"Functions ({len(unchanged_entries)} standard run)"))
    visible_unchanged: Sequence[FunctionPlanEntry] = visible_entries(
        entries=unchanged_entries, options=display_options
    )
    for function_entry in visible_unchanged:
        lines = _format_function_entry(
            lines=lines,
            function_entry=function_entry,
            show_details=False,
            name_column_width=name_column_width,
        )
    lines = append_overflow_line(
        lines=lines,
        total_count=len(unchanged_entries),
        visible_count=len(visible_unchanged),
        indent="  ",
        options=display_options,
    )
    return lines


def _format_function_entry(
    *,
    lines: list[str],
    function_entry: FunctionPlanEntry,
    show_details: bool,
    name_column_width: int,
) -> list[str]:
    """Append one function line and optional change details."""

    function_kind: str = (
        "table function"
        if function_entry.return_columns
        else f"{function_entry.language.value} udf"
    )
    lines.append(
        _format_name_value_line(
            name=function_entry.name,
            value=function_kind,
            name_column_width=name_column_width,
        )
    )
    if not show_details:
        return lines
    if function_entry.reason == PlanReason.FIRST_RUN:
        lines.append("    reason: first run")
    elif function_entry.reason == PlanReason.FULL_REFRESH:
        lines.append("    reason: full refresh")
    elif function_entry.reason == PlanReason.QUERY_CHANGED:
        if function_entry.backfill.action != BackfillAction.FORWARD_ONLY:
            duration: str = function_entry.backfill.duration or "full"
            policy_value: str = _backfill_value(
                action=function_entry.backfill.action, duration=duration
            )
            lines.append(f"    policy: replay_on_change={policy_value}")
        if function_entry.previous_query_sql is not None:
            style: CliStyle = CliStyle(use_color=True)
            lines.append(style.label("    query diff:"))
            lines.extend(
                format_query_diff(
                    previous=function_entry.previous_query_sql,
                    current=function_entry.fingerprint_query_sql,
                )
            )
    return lines


def _format_warnings(
    *,
    lines: list[str],
    plan: PlanOutput,
    include_standard_freshness_diagnostics: bool,
) -> list[str]:
    """Append the warnings section."""

    warning_entries: list[PlanWarning] = [
        warning
        for warning in plan.warnings
        if warning.severity != WarningSeverity.INFO
        and (
            include_standard_freshness_diagnostics
            or not warning.message.startswith(_STALE_INPUT_WARNING_TITLE)
        )
    ]
    if not warning_entries:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(style.warning_strong(f"Warnings ({len(warning_entries)})"))
    warning: PlanWarning
    for warning in warning_entries:
        if warning.model_name is not None:
            lines.append(f"  {style.object_name(warning.model_name)}")
        message_lines: list[str] = warning.message.split("\n")
        lines.append(f"  {style.warning(f'- {message_lines[0]}')}")
        continuation: str
        for continuation in message_lines[1:]:
            lines.append(f"    {style.warning(continuation)}")
    return lines


def _format_virtual_metadata(
    *,
    lines: list[str],
    plan: PlanOutput,
    section_header_style: Callable[[str], str],
    display_options: DisplayOptions,
) -> list[str]:
    """Append a virtual planner metadata section when present."""

    virtual_environment_name: object | None = plan.metadata.get("virtual_environment_name")
    if not isinstance(virtual_environment_name, str):
        return lines
    virtual_environment_status: str = str(
        plan.metadata.get("virtual_environment_status", "unknown")
    )
    raw_stale_model_names: object | None = plan.metadata.get("virtual_stale_model_names")
    stale_model_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_stale_model_names)
        if isinstance(raw_stale_model_names, (tuple, list))
        else ()
    )
    raw_stale_root_names: object | None = plan.metadata.get("virtual_stale_root_names")
    stale_root_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_stale_root_names)
        if isinstance(raw_stale_root_names, (tuple, list))
        else ()
    )
    raw_remaining_stale_model_names: object | None = plan.metadata.get(
        "virtual_remaining_stale_model_names"
    )
    remaining_stale_model_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_remaining_stale_model_names)
        if isinstance(raw_remaining_stale_model_names, (tuple, list))
        else ()
    )
    raw_observed_source_names: object | None = plan.metadata.get(
        "virtual_source_freshness_observed_source_names"
    )
    observed_source_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_observed_source_names)
        if isinstance(raw_observed_source_names, (tuple, list))
        else ()
    )
    raw_incomplete_source_names: object | None = plan.metadata.get(
        "virtual_source_freshness_incomplete_source_names"
    )
    raw_unchanged_source_names: object | None = plan.metadata.get(
        "virtual_source_freshness_unchanged_source_names"
    )
    unchanged_source_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_unchanged_source_names)
        if isinstance(raw_unchanged_source_names, (tuple, list))
        else ()
    )
    incomplete_source_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_incomplete_source_names)
        if isinstance(raw_incomplete_source_names, (tuple, list))
        else ()
    )
    raw_incomplete_model_names: object | None = plan.metadata.get(
        "virtual_source_freshness_incomplete_model_names"
    )
    incomplete_model_names: tuple[str, ...] = (
        tuple(str(item) for item in raw_incomplete_model_names)
        if isinstance(raw_incomplete_model_names, (tuple, list))
        else ()
    )
    lines.append("")
    lines.append(section_header_style("Virtual environment"))
    lines.append(f"  name: {virtual_environment_name}")
    lines.append(f"  status: {virtual_environment_status}")
    if observed_source_names or incomplete_source_names:
        lines.append(f"  source freshness observed: {len(observed_source_names)}")
        if observed_source_names:
            observed_source_set: str = _format_capped_name_list(
                names=observed_source_names,
                display_options=display_options,
            )
            lines.append(f"  source freshness observed set: {observed_source_set}")
        lines.append(f"  source freshness unchanged: {len(unchanged_source_names)}")
        if unchanged_source_names:
            unchanged_source_set: str = _format_capped_name_list(
                names=unchanged_source_names,
                display_options=display_options,
            )
            lines.append(f"  source freshness unchanged set: {unchanged_source_set}")
        lines.append(f"  source freshness incomplete: {len(incomplete_source_names)}")
        if incomplete_source_names:
            incomplete_source_set: str = _format_capped_name_list(
                names=incomplete_source_names,
                display_options=display_options,
            )
            lines.append(f"  source freshness incomplete set: {incomplete_source_set}")
        if incomplete_model_names:
            incomplete_model_set: str = _format_capped_name_list(
                names=incomplete_model_names,
                display_options=display_options,
            )
            lines.append(f"  source freshness incomplete models: {incomplete_model_set}")
    lines.append(f"  stale roots: {len(stale_root_names)}")
    if stale_root_names:
        stale_root_set: str = _format_capped_name_list(
            names=stale_root_names,
            display_options=display_options,
        )
        lines.append(f"  stale root set: {stale_root_set}")
    lines.append(f"  stale models: {len(stale_model_names)}")
    if stale_model_names:
        stale_model_set: str = _format_capped_name_list(
            names=stale_model_names,
            display_options=display_options,
        )
        lines.append(f"  stale model set: {stale_model_set}")
    if remaining_stale_model_names:
        remaining_stale_set: str = _format_capped_name_list(
            names=remaining_stale_model_names,
            display_options=display_options,
        )
        lines.append(f"  remaining stale after selection: {remaining_stale_set}")
    return lines


def _format_standard_source_freshness_metadata(
    *,
    lines: list[str],
    plan: PlanOutput,
    section_header_style: Callable[[str], str],
    display_options: DisplayOptions,
) -> list[str]:
    raw_metadata: object | None = plan.metadata.get("standard_source_freshness")
    if not isinstance(raw_metadata, dict):
        return lines
    source_freshness_metadata: dict[str, object] = cast(dict[str, object], raw_metadata)
    observed_source_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("observed_source_names")
    )
    changed_source_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("changed_source_names")
    )
    unchanged_source_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("unchanged_source_names")
    )
    unknown_source_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("unknown_source_names")
    )
    age_warning_source_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("age_warning_source_names")
    )
    age_error_source_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("age_error_source_names")
    )
    stale_model_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("stale_model_names")
    )
    blocked_model_names: tuple[str, ...] = _metadata_string_tuple(
        source_freshness_metadata.get("blocked_model_names")
    )
    if not observed_source_names and not unknown_source_names:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(section_header_style("Source freshness"))
    lines.append(
        _source_freshness_count_line(style=style, label="observed", names=observed_source_names)
    )
    if observed_source_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="observed set",
                names=observed_source_names,
                display_options=display_options,
            )
        )
    lines.append(
        _source_freshness_count_line(
            style=style, label="changed", names=changed_source_names, warn_nonzero=True
        )
    )
    if changed_source_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="changed set",
                names=changed_source_names,
                display_options=display_options,
                warn=True,
            )
        )
    lines.append(
        _source_freshness_count_line(style=style, label="unchanged", names=unchanged_source_names)
    )
    if unchanged_source_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="unchanged set",
                names=unchanged_source_names,
                display_options=display_options,
            )
        )
    lines.append(
        _source_freshness_count_line(
            style=style, label="unknown", names=unknown_source_names, warn_nonzero=True
        )
    )
    if unknown_source_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="unknown set",
                names=unknown_source_names,
                display_options=display_options,
                warn=True,
            )
        )
    if age_warning_source_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="age warnings",
                names=age_warning_source_names,
                display_options=display_options,
                warn=True,
            )
        )
    if age_error_source_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="age errors",
                names=age_error_source_names,
                display_options=display_options,
                warn=True,
            )
        )
    if stale_model_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="source-stale models",
                names=stale_model_names,
                display_options=display_options,
                warn=True,
            )
        )
    if blocked_model_names:
        lines.append(
            _source_freshness_set_line(
                style=style,
                label="source-blocked models",
                names=blocked_model_names,
                display_options=display_options,
                warn=True,
            )
        )
    return lines


def _format_standard_remaining_stale_metadata(
    *,
    lines: list[str],
    plan: PlanOutput,
    section_header_style: Callable[[str], str],
    display_options: DisplayOptions,
) -> list[str]:
    remaining_stale_model_names: tuple[str, ...] = _metadata_string_tuple(
        plan.metadata.get("standard_remaining_stale_model_names")
    )
    if not remaining_stale_model_names:
        return lines
    style: CliStyle = CliStyle(use_color=True)
    lines.append("")
    lines.append(section_header_style("Remaining stale"))
    lines.append(style.muted(f"  models outside selection: {len(remaining_stale_model_names)}"))
    lines.append(
        style.muted(
            "  model set: "
            + _format_capped_name_list(
                names=remaining_stale_model_names,
                display_options=display_options,
                name_style=style.muted,
            )
        )
    )
    return lines


def _metadata_string_tuple(raw_value: object | None) -> tuple[str, ...]:
    return tuple(str(item) for item in raw_value) if isinstance(raw_value, (tuple, list)) else ()


def _source_freshness_count_line(
    *,
    style: CliStyle,
    label: str,
    names: tuple[str, ...],
    warn_nonzero: bool = False,
) -> str:
    count_text: str = str(len(names))
    styled_count: str
    if warn_nonzero and names:
        styled_count = style.warning(count_text)
    elif not names:
        styled_count = style.muted(count_text)
    else:
        styled_count = count_text
    return f"  {style.label(label + ':')} {styled_count}"


def _source_freshness_set_line(
    *,
    style: CliStyle,
    label: str,
    names: tuple[str, ...],
    display_options: DisplayOptions,
    warn: bool = False,
) -> str:
    formatted_names: str = _format_capped_name_list(
        names=names,
        display_options=display_options,
        name_style=style.warning if warn else style.object_name,
    )
    return f"  {style.label(label + ':')} {formatted_names}"


def _format_capped_name_list(
    *,
    names: tuple[str, ...],
    display_options: DisplayOptions,
    name_style: Callable[[str], str] | None = None,
) -> str:
    """Format a capped comma-separated name list."""

    limit: int | None = display_options.max_entries_per_section
    visible_names: tuple[str, ...] = names if limit is None else names[:limit]
    remaining_count: int = len(names) - len(visible_names)
    rendered_names: tuple[str, ...] = (
        visible_names if name_style is None else tuple(name_style(name) for name in visible_names)
    )
    base: str = ", ".join(rendered_names)
    if remaining_count <= 0:
        return base
    return f"{base}, ... (+{remaining_count} more; use {display_options.overflow_flag} to show all)"


def _resolve_name_column_width(
    *, plan: PlanOutput, python_plan_entries: tuple[PythonPlanEntry, ...] = ()
) -> int:
    names: list[str] = [
        entry.name for entry in (*plan.dependency_baseline_entries, *plan.model_entries)
    ]
    names.extend(entry.name for entry in plan.function_entries)
    names.extend(entry.name for entry in python_plan_entries)
    return resolve_name_column_width(names=names)


def _format_name_value_line(*, name: str, value: str, name_column_width: int) -> str:
    style: CliStyle = CliStyle(use_color=True)
    return format_aligned_name_value(
        plain_name=name,
        styled_name=style.object_name(name),
        value=value,
        name_column_width=name_column_width,
    )


def _format_schema_findings(findings: tuple[SchemaFinding, ...]) -> list[str]:
    """Format schema findings as indented diff lines."""

    style: CliStyle = CliStyle(use_color=True)
    lines: list[str] = []
    finding: SchemaFinding
    for finding in findings:
        symbol: str = _SCHEMA_CHANGE_SYMBOLS.get(finding.kind, "?")
        type_info: str = ""
        if finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
            type_info = f"  {finding.expected_type} \u2192 {finding.actual_type}"
        elif finding.kind == SchemaChangeKind.COLUMN_ADDED:
            type_info = f"  {finding.expected_type}" if finding.expected_type else ""
        kind_label: str = _schema_kind_label(finding.kind)
        line: str = f"      {symbol} {finding.column_name}{type_info}   ({kind_label})"
        if finding.kind == SchemaChangeKind.COLUMN_ADDED:
            lines.append(style.success(line))
        elif finding.kind == SchemaChangeKind.COLUMN_REMOVED:
            lines.append(style.error(line))
        elif finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
            lines.append(style.warning(line))
        else:
            lines.append(line)
    return lines


def _schema_kind_label(kind: SchemaChangeKind) -> str:
    """Human-readable schema change kind."""

    if kind == SchemaChangeKind.COLUMN_ADDED:
        return "added"
    if kind == SchemaChangeKind.COLUMN_REMOVED:
        return "removed"
    if kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
        return "type changed"
    return str(kind)


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""

    return _ANSI_ESCAPE_PATTERN.sub("", text)
