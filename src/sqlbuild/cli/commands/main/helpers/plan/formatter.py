"""Plan output formatting grouped by reason with inline detail."""

from __future__ import annotations

import difflib
import re
from collections import Counter

from sqlbuild.compiler.planner.models import (
    CascadeResult,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    IncrementalMode,
    MaterializationType,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    WarningSeverity,
)
from sqlbuild.shared.helpers.colors import blue_bold, green, green_bold, red, yellow, yellow_bold

_REASON_GROUP_ORDER: tuple[PlanReason, ...] = (
    PlanReason.QUERY_CHANGED,
    PlanReason.SCHEMA_CHANGED,
    PlanReason.FIRST_RUN,
)

_REASON_GROUP_LABELS: dict[PlanReason, str] = {
    PlanReason.QUERY_CHANGED: "Query changed",
    PlanReason.SCHEMA_CHANGED: "Schema changed",
    PlanReason.FIRST_RUN: "First run",
}

_ANSI_ESCAPE_PATTERN: re.Pattern[str] = re.compile(r"\033\[[0-9;]*m")

_SCHEMA_CHANGE_SYMBOLS: dict[SchemaChangeKind, str] = {
    SchemaChangeKind.COLUMN_ADDED: "+",
    SchemaChangeKind.COLUMN_REMOVED: "-",
    SchemaChangeKind.COLUMN_TYPE_CHANGED: "~",
}


def format_plan(plan: PlanOutput, *, full_refresh: bool = False, use_color: bool = True) -> str:
    """Format plan output grouped by reason with inline detail."""

    lines: list[str] = []

    if full_refresh:
        _format_full_refresh(lines, plan)
        result: str = "\n".join(lines)
        return result if use_color else _strip_ansi(result)

    active: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]
    selected_count: int = _selected_count(plan)

    header: str = f"Plan ready ({selected_count} selected)"
    lines.append(green_bold(header))

    normal: list[ModelPlanEntry] = _collect_normal(active)
    cascade: list[ModelPlanEntry] = _collect_upstream_changed(active)
    groups: dict[PlanReason, list[ModelPlanEntry]] = _group_by_reason(active, cascade)

    _format_functions(lines, plan)

    if normal:
        lines.append("")
        _format_normal_section(lines, normal)

    reason: PlanReason
    for reason in _REASON_GROUP_ORDER:
        entries: list[ModelPlanEntry] | None = groups.get(reason)
        if not entries:
            continue
        label: str = _REASON_GROUP_LABELS[reason]
        lines.append("")
        lines.append(green_bold(f"{label} ({len(entries)})"))
        entry: ModelPlanEntry
        for entry in entries:
            _format_detail_entry(lines, entry, reason)

    if cascade:
        lines.append("")
        lines.append(green_bold(f"Upstream changed ({len(cascade)})"))
        entry_c: ModelPlanEntry
        for entry_c in cascade:
            _format_upstream_changed_entry(lines, entry_c)

    _format_seeds(lines, plan)
    _format_warnings(lines, plan)

    output: str = "\n".join(lines)
    return output if use_color else _strip_ansi(output)


def _format_full_refresh(lines: list[str], plan: PlanOutput) -> None:
    """Format the full refresh variant of plan output."""

    selected_count: int = _selected_count(plan)
    active: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]

    lines.append(green_bold(f"Plan ready (full refresh, {selected_count} selected)"))

    _format_functions(lines, plan)
    lines.append("")

    counts: Counter[str] = Counter()
    entry: ModelPlanEntry
    for entry in active:
        label: str = _materialization_label(entry)
        counts[label] += 1

    lines.append(green_bold(f"Full refresh ({len(active)})"))
    count_label: str
    count_value: int
    for count_label, count_value in counts.most_common():
        lines.append(f"  {count_value:>3} {count_label}")

    _format_seeds(lines, plan)


def _selected_count(plan: PlanOutput) -> int:
    """Count selected executable resources shown in plan output."""

    return len(plan.model_entries) + len(plan.seed_entries) + len(plan.function_entries)


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


def _format_normal_section(lines: list[str], entries: list[ModelPlanEntry]) -> None:
    """Format the Normal aggregate counts section."""

    counts: Counter[str] = Counter()
    entry: ModelPlanEntry
    for entry in entries:
        label: str = _materialization_label(entry)
        counts[label] += 1

    lines.append(green_bold(f"Normal ({len(entries)})"))
    count_label: str
    count_value: int
    for count_label, count_value in counts.most_common():
        lines.append(f"  {count_value:>3} {count_label}")


def _materialization_label(entry: ModelPlanEntry) -> str:
    """Build the display label for a model's materialization in aggregate counts."""

    if entry.materialization_type == MaterializationType.VIEW:
        return MaterializationType.VIEW.value
    if entry.materialization_type == MaterializationType.TABLE:
        return MaterializationType.TABLE.value
    if entry.materialization_type == MaterializationType.INCREMENTAL:
        return _incremental_label(entry)
    if entry.materialization_type == MaterializationType.CUSTOM:
        custom_name: str = entry.custom_materialization_name or MaterializationType.CUSTOM.value
        return f"{custom_name} (custom)"
    return entry.materialization_type.value


def _incremental_label(entry: ModelPlanEntry) -> str:
    """Build the display label for an incremental model."""

    strategy: str = entry.incremental_strategy or MaterializationType.INCREMENTAL.value
    parts: list[str] = []
    if entry.cursor_type is not None:
        parts.append(entry.cursor_type)
    if entry.incremental_mode == IncrementalMode.MICROBATCH:
        parts.append("microbatch")
    if parts:
        return f"{strategy} ({', '.join(parts)})"
    return strategy


def _format_detail_entry(
    lines: list[str],
    entry: ModelPlanEntry,
    reason: PlanReason,
) -> None:
    """Format a per-model entry with action text and detail lines."""

    if reason == PlanReason.FIRST_RUN:
        mat_label: str = _materialization_label(entry)
        lines.append(f"  {blue_bold(entry.name):<40s} {mat_label}")
        return

    action_text: str = _action_text(entry)
    lines.append(f"  {blue_bold(entry.name):<40s} {action_text}")
    _append_cursor_detail(
        lines,
        entry,
        show_range=entry.backfill.action != BackfillAction.FULL,
    )
    _append_policy_line(lines, entry)
    _append_schema_diff(lines, entry)
    _append_query_diff(lines, entry)


def _format_upstream_changed_entry(lines: list[str], entry: ModelPlanEntry) -> None:
    """Format a per-model entry in the Upstream changed group."""

    cascade: CascadeResult | None = entry.cascade
    action_text: str = _cascade_action_text(cascade)
    lines.append(f"  {blue_bold(entry.name):<40s} {action_text}")
    _append_cursor_detail(
        lines,
        entry,
        show_range=cascade is None or cascade.effective_action != BackfillAction.FULL,
    )
    if cascade is not None and cascade.root_cause is not None:
        cause_desc: str = _cascade_cause_description(cascade)
        lines.append(f"    cause: {cause_desc}")


def _append_cursor_detail(
    lines: list[str], entry: ModelPlanEntry, *, show_range: bool = True
) -> None:
    """Append cursor column, mode, and range detail lines."""

    if entry.cursor_column is not None:
        lines.append(f"    cursor: {entry.cursor_column}")
    if entry.incremental_mode == IncrementalMode.MICROBATCH:
        lines.append(f"    mode: {IncrementalMode.MICROBATCH.value}")
    if show_range and entry.cursor_bounds is not None:
        lines.append(f"    range: {entry.cursor_bounds.start} \u2192 {entry.cursor_bounds.end}")


def _append_policy_line(lines: list[str], entry: ModelPlanEntry) -> None:
    """Append the policy line if a backfill policy triggered."""

    if entry.backfill.action == BackfillAction.WARN_ONLY:
        return
    duration: str = entry.backfill.duration or "full"
    policy_value: str = _backfill_value(entry.backfill.action, duration)
    if entry.reason == PlanReason.QUERY_CHANGED:
        lines.append(f"    policy: query_change_backfill={policy_value}")
    elif entry.reason == PlanReason.SCHEMA_CHANGED:
        lines.append(f"    policy: schema_change_backfill={policy_value}")


def _append_schema_diff(lines: list[str], entry: ModelPlanEntry) -> None:
    """Append schema diff lines if findings exist."""

    if not entry.schema_findings:
        return
    lines.append("    schema diff:")
    lines.extend(_format_schema_findings(entry.schema_findings))


def _append_query_diff(lines: list[str], entry: ModelPlanEntry) -> None:
    """Append query diff lines if previous SQL is available."""

    if entry.previous_query_sql is None:
        return
    lines.append("    query diff:")
    lines.extend(_format_query_diff(entry.previous_query_sql, entry.fingerprint_query_sql))


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
    if reason == PlanReason.SCHEMA_CHANGED:
        return "schema changed"
    if reason == PlanReason.FIRST_RUN:
        return "first run"
    if reason == PlanReason.FULL_REFRESH:
        return "full refresh"
    return ""


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


def _backfill_value(action: BackfillAction, duration: str) -> str:
    """Format a backfill action as a policy value string."""

    if action == BackfillAction.BOUNDED:
        return f"bounded-{duration}"
    return str(action)


def _format_seeds(lines: list[str], plan: PlanOutput) -> None:
    """Append the seeds section."""

    if not plan.seed_entries:
        return
    lines.append("")
    lines.append(green_bold(f"Seeds ({len(plan.seed_entries)})"))
    seed_entry: object
    for seed_entry in plan.seed_entries:
        lines.append(f"  {getattr(seed_entry, 'name', str(seed_entry))}")


def _format_functions(lines: list[str], plan: PlanOutput) -> None:
    """Append the functions section."""

    if not plan.function_entries:
        return
    changed_entries: list[FunctionPlanEntry] = [
        entry for entry in plan.function_entries if entry.reason != PlanReason.NO_CHANGE
    ]
    unchanged_entries: list[FunctionPlanEntry] = [
        entry for entry in plan.function_entries if entry.reason == PlanReason.NO_CHANGE
    ]
    if changed_entries:
        lines.append("")
        lines.append(green_bold(f"Function changed ({len(changed_entries)})"))
        function_entry: FunctionPlanEntry
        for function_entry in changed_entries:
            _format_function_entry(lines, function_entry, show_details=True)
    if not unchanged_entries:
        return
    lines.append("")
    lines.append(green_bold(f"Functions ({len(unchanged_entries)})"))
    for function_entry in unchanged_entries:
        _format_function_entry(lines, function_entry, show_details=False)


def _format_function_entry(
    lines: list[str], function_entry: FunctionPlanEntry, *, show_details: bool
) -> None:
    """Append one function line and optional change details."""

    function_kind: str = (
        "table function"
        if function_entry.return_columns
        else f"{function_entry.language.value} udf"
    )
    lines.append(f"  {blue_bold(function_entry.name):<40s} {function_kind}")
    if not show_details:
        return
    if function_entry.reason == PlanReason.FIRST_RUN:
        lines.append("    reason: first run")
    elif function_entry.reason == PlanReason.FULL_REFRESH:
        lines.append("    reason: full refresh")
    elif function_entry.reason == PlanReason.QUERY_CHANGED:
        if function_entry.backfill.action != BackfillAction.WARN_ONLY:
            duration: str = function_entry.backfill.duration or "full"
            policy_value: str = _backfill_value(function_entry.backfill.action, duration)
            lines.append(f"    policy: query_change_backfill={policy_value}")
        if function_entry.previous_query_sql is not None:
            lines.append("    query diff:")
            lines.extend(
                _format_query_diff(
                    function_entry.previous_query_sql, function_entry.fingerprint_query_sql
                )
            )


def _format_warnings(lines: list[str], plan: PlanOutput) -> None:
    """Append the warnings section."""

    warning_entries: list[PlanWarning] = [
        w for w in plan.warnings if w.severity != WarningSeverity.INFO
    ]
    if not warning_entries:
        return
    lines.append("")
    lines.append(yellow_bold(f"Warnings ({len(warning_entries)})"))
    warning: PlanWarning
    for warning in warning_entries:
        if warning.model_name is not None:
            lines.append(f"  {blue_bold(warning.model_name)}")
        lines.append(f"  {yellow(f'- {warning.message}')}")


def _format_schema_findings(findings: tuple[SchemaFinding, ...]) -> list[str]:
    """Format schema findings as indented diff lines."""

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
            lines.append(green(line))
        elif finding.kind == SchemaChangeKind.COLUMN_REMOVED:
            lines.append(red(line))
        elif finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
            lines.append(yellow(line))
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


def _format_query_diff(previous: str, current: str) -> list[str]:
    """Format a unified diff between previous and current SQL."""

    previous_lines: list[str] = previous.splitlines(keepends=True)
    current_lines: list[str] = current.splitlines(keepends=True)
    diff_lines: list[str] = list(
        difflib.unified_diff(previous_lines, current_lines, fromfile="previous", tofile="current")
    )
    result: list[str] = []
    line: str
    for line in diff_lines:
        stripped: str = line.rstrip("\n")
        formatted: str = f"      {stripped}"
        if stripped.startswith("+") and not stripped.startswith("+++"):
            result.append(green(formatted))
        elif stripped.startswith("-") and not stripped.startswith("---"):
            result.append(red(formatted))
        else:
            result.append(formatted)
    return result


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""

    return _ANSI_ESCAPE_PATTERN.sub("", text)
