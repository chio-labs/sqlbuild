"""Plan output formatting grouped by reason with inline detail."""

from __future__ import annotations

import difflib

from sqlbuild.cli.commands.main.shared.helpers.colors import (
    blue_bold,
    bold,
    green,
    red,
    yellow,
    yellow_bold,
)
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    WarningSeverity,
)

_REASON_GROUP_LABELS: dict[PlanReason, str] = {
    PlanReason.QUERY_CHANGED: "Query changed",
    PlanReason.SCHEMA_CHANGED: "Schema changed",
    PlanReason.FIRST_RUN: "First run",
    PlanReason.FULL_REFRESH: "Full refresh",
    PlanReason.NORMAL_INCREMENTAL: "Normal incremental",
}

_REASON_GROUP_ORDER: tuple[PlanReason, ...] = (
    PlanReason.QUERY_CHANGED,
    PlanReason.SCHEMA_CHANGED,
    PlanReason.FIRST_RUN,
    PlanReason.FULL_REFRESH,
    PlanReason.NORMAL_INCREMENTAL,
)

_SCHEMA_CHANGE_SYMBOLS: dict[SchemaChangeKind, str] = {
    SchemaChangeKind.COLUMN_ADDED: "+",
    SchemaChangeKind.COLUMN_REMOVED: "-",
    SchemaChangeKind.COLUMN_TYPE_CHANGED: "~",
}


def format_plan(plan: PlanOutput) -> str:
    """Format plan output grouped by reason with inline detail."""

    lines: list[str] = []
    will_run: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]
    normal_count: int = _count_normal(plan.model_entries)
    selected_count: int = len(plan.model_entries) + len(plan.seed_entries)
    warning_entries: list[PlanWarning] = [
        w for w in plan.warnings if w.severity != WarningSeverity.INFO
    ]

    lines.append(green("Plan ready"))
    lines.append("")
    lines.append(f"Selected: {selected_count}")
    if normal_count > 0:
        lines.append(f"Normal: {normal_count}")

    groups: dict[PlanReason, list[ModelPlanEntry]] = _group_by_reason(will_run)
    reason: PlanReason
    for reason in _REASON_GROUP_ORDER:
        entries: list[ModelPlanEntry] | None = groups.get(reason)
        if entries is None:
            continue
        label: str = _REASON_GROUP_LABELS.get(reason, str(reason))
        lines.append("")
        is_first_run: bool = reason == PlanReason.FIRST_RUN
        _format_header_line(lines, label, len(entries), is_first_run)
        _format_group_entries(lines, entries, is_first_run, plan)

    _format_warnings(lines, warning_entries, plan)

    return "\n".join(lines)


def _count_normal(entries: tuple[ModelPlanEntry, ...]) -> int:
    """Count models that will run with no special action."""

    count: int = 0
    entry: ModelPlanEntry
    for entry in entries:
        if entry.action == PlanAction.SKIP:
            continue
        if entry.reason in (PlanReason.NO_CHANGE, PlanReason.NORMAL_INCREMENTAL):
            count += 1
    return count


def _group_by_reason(
    entries: list[ModelPlanEntry],
) -> dict[PlanReason, list[ModelPlanEntry]]:
    """Group will-run entries by reason, excluding normal/no-change."""

    groups: dict[PlanReason, list[ModelPlanEntry]] = {}
    entry: ModelPlanEntry
    for entry in entries:
        if entry.reason in (PlanReason.NO_CHANGE, PlanReason.NORMAL_INCREMENTAL):
            continue
        groups.setdefault(entry.reason, []).append(entry)
    return groups


def _format_header_line(lines: list[str], label: str, count: int, is_first_run: bool) -> None:
    """Append a group header with count, or inline count for first run."""

    if is_first_run:
        lines.append(bold(f"{label}: {count}"))
    else:
        lines.append(bold(f"{label} ({count})"))


def _format_group_entries(
    lines: list[str],
    entries: list[ModelPlanEntry],
    is_first_run: bool,
    plan: PlanOutput,
) -> None:
    """Append formatted entries for one reason group."""

    entry: ModelPlanEntry
    for entry in entries:
        if is_first_run:
            lines.append(f"  {blue_bold(entry.name)}")
            continue
        action_text: str = _action_text(entry)
        lines.append(f"  {blue_bold(entry.name):<40s} {action_text}")
        _format_entry_detail(lines, entry)


def _format_entry_detail(lines: list[str], entry: ModelPlanEntry) -> None:
    """Append cursor, policy, schema diff, and query diff for one entry."""

    if entry.cursor_bounds is not None and entry.cursor_column is not None:
        lines.append(f"    cursor: {entry.cursor_column}")
        lines.append(f"    range: {entry.cursor_bounds.start} \u2192 {entry.cursor_bounds.end}")
    policy: str | None = _policy_label(entry)
    if policy is not None:
        lines.append(f"    policy: {policy}")
    if entry.schema_findings:
        lines.append("    schema diff:")
        lines.extend(_format_schema_findings(entry.schema_findings))
    if entry.previous_query_sql is not None:
        lines.append("    query diff:")
        lines.extend(_format_query_diff(entry.previous_query_sql, entry.resolved_sql))


def _format_warnings(
    lines: list[str],
    warning_entries: list[PlanWarning],
    plan: PlanOutput,
) -> None:
    """Append the warnings section."""

    if not warning_entries:
        return
    lines.append("")
    lines.append(yellow_bold(f"Warnings ({len(warning_entries)})"))
    warning: PlanWarning
    for warning in warning_entries:
        if warning.model_name is not None:
            lines.append(f"  {blue_bold(warning.model_name)}")
        lines.append(f"  {yellow(f'- {warning.message}')}")
        warning_model: ModelPlanEntry | None = _find_entry(plan, warning.model_name)
        if warning_model is not None and warning_model.schema_findings:
            lines.append("    schema diff:")
            lines.extend(_format_schema_findings(warning_model.schema_findings))


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


def _policy_label(entry: ModelPlanEntry) -> str | None:
    """Format the policy that caused the action, if any."""

    if entry.backfill.action == BackfillAction.WARN_ONLY:
        return None
    duration: str = entry.backfill.duration or "full"
    if entry.reason == PlanReason.QUERY_CHANGED:
        return f"query_change_backfill={_backfill_value(entry.backfill.action, duration)}"
    if entry.reason == PlanReason.SCHEMA_CHANGED:
        return f"schema_change_backfill={_backfill_value(entry.backfill.action, duration)}"
    return None


def _backfill_value(action: BackfillAction, duration: str) -> str:
    """Format a backfill action as a policy value string."""

    if action == BackfillAction.BOUNDED:
        return f"bounded({duration})"
    return str(action)


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


def _find_entry(plan: PlanOutput, model_name: str | None) -> ModelPlanEntry | None:
    """Find a model plan entry by name."""

    if model_name is None:
        return None
    entry: ModelPlanEntry
    for entry in plan.model_entries:
        if entry.name == model_name:
            return entry
    return None
