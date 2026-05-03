"""Plan output formatting for compact and verbose modes."""

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

_REASON_LABELS: dict[PlanReason, str] = {
    PlanReason.FIRST_RUN: "new model",
    PlanReason.FULL_REFRESH: "full refresh",
    PlanReason.QUERY_CHANGED: "query changed",
    PlanReason.SCHEMA_CHANGED: "schema changed",
    PlanReason.NORMAL_INCREMENTAL: "normal incremental",
    PlanReason.NO_CHANGE: "no change",
}

_ACTION_LABELS: dict[PlanAction, str] = {
    PlanAction.CREATE_VIEW: "create view",
    PlanAction.CREATE_TABLE: "create table",
    PlanAction.INCREMENTAL_APPEND: "incremental append",
    PlanAction.INCREMENTAL_DELETE_INSERT: "incremental delete+insert",
    PlanAction.INCREMENTAL_MERGE: "incremental merge",
    PlanAction.LOAD_SEED: "load seed",
    PlanAction.SKIP: "skip",
}

_SCHEMA_CHANGE_SYMBOLS: dict[SchemaChangeKind, str] = {
    SchemaChangeKind.COLUMN_ADDED: "+",
    SchemaChangeKind.COLUMN_REMOVED: "-",
    SchemaChangeKind.COLUMN_TYPE_CHANGED: "~",
}


def format_plan_compact(plan: PlanOutput) -> str:
    """Format plan output in compact mode."""

    lines: list[str] = []
    will_run: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]
    warning_entries: list[PlanWarning] = [
        w for w in plan.warnings if w.severity != WarningSeverity.INFO
    ]

    lines.append(green("Plan ready"))
    lines.append("")
    lines.append(f"Selected models: {len(plan.model_entries) + len(plan.seed_entries)}")
    lines.append(f"Will run: {len(will_run)}")
    if warning_entries:
        lines.append(f"Warnings: {len(warning_entries)}")

    if will_run:
        lines.append("")
        lines.append(bold("Will run"))
        entry: ModelPlanEntry
        for entry in will_run:
            lines.append("")
            lines.append(blue_bold(entry.name))
            lines.append(f"  reason: {_reason_label(entry.reason)}")
            lines.append(f"  action: {_action_label(entry)}")
            policy: str | None = _policy_label(entry)
            if policy is not None:
                lines.append(f"  policy: {policy}")

    if warning_entries:
        lines.append("")
        lines.append(yellow_bold("Warnings"))
        warning: PlanWarning
        for warning in warning_entries:
            lines.append("")
            if warning.model_name is not None:
                lines.append(blue_bold(warning.model_name))
            lines.append(f"  {yellow(warning.message)}")

    diff_models: list[str] = [e.name for e in will_run if e.previous_query_sql is not None]
    if diff_models:
        lines.append("")
        lines.append("Diffs available for:")
        name: str
        for name in diff_models:
            lines.append(f"  {name}")
        lines.append("")
        lines.append("Run `sqb plan --verbose` to show full diffs.")

    return "\n".join(lines)


def format_plan_verbose(plan: PlanOutput) -> str:
    """Format plan output in verbose mode."""

    lines: list[str] = []
    will_run: list[ModelPlanEntry] = [e for e in plan.model_entries if e.action != PlanAction.SKIP]
    warning_entries: list[PlanWarning] = [
        w for w in plan.warnings if w.severity != WarningSeverity.INFO
    ]

    lines.append(green("Plan ready"))
    lines.append("")
    lines.append(f"Selected models: {len(plan.model_entries) + len(plan.seed_entries)}")
    lines.append(f"Will run: {len(will_run)}")
    if warning_entries:
        lines.append(f"Warnings: {len(warning_entries)}")

    if will_run:
        lines.append("")
        lines.append(bold("Will run"))
        entry: ModelPlanEntry
        for entry in will_run:
            lines.append("")
            lines.append(blue_bold(entry.name))
            lines.append(f"  reason: {_reason_label(entry.reason)}")
            lines.append(f"  action: {_action_label(entry)}")
            policy: str | None = _policy_label(entry)
            if policy is not None:
                lines.append(f"  policy: {policy}")
            if entry.cursor_bounds is not None:
                lines.append(f"  cursor: {entry.cursor_column or 'unknown'}")
                lines.append(
                    f"  bounded range: {entry.cursor_bounds.start} \u2192 {entry.cursor_bounds.end}"
                )
            if entry.schema_findings:
                lines.append("  schema diff:")
                lines.extend(_format_schema_findings(entry.schema_findings))
            if entry.previous_query_sql is not None:
                lines.append("  query diff:")
                lines.extend(_format_query_diff(entry.previous_query_sql, entry.resolved_sql))
            if entry.reason == PlanReason.FIRST_RUN:
                lines.append("  no previous fingerprint")

    if warning_entries:
        lines.append("")
        lines.append(yellow_bold("Warnings"))
        warning: PlanWarning
        for warning in warning_entries:
            lines.append("")
            if warning.model_name is not None:
                lines.append(blue_bold(warning.model_name))
            lines.append(f"  {yellow(warning.message)}")
            warning_model: ModelPlanEntry | None = _find_entry(plan, warning.model_name)
            if warning_model is not None and warning_model.schema_findings:
                lines.append("  schema diff:")
                lines.extend(_format_schema_findings(warning_model.schema_findings))

    return "\n".join(lines)


def _reason_label(reason: PlanReason) -> str:
    """Human-readable reason label."""

    return _REASON_LABELS.get(reason, str(reason))


def _action_label(entry: ModelPlanEntry) -> str:
    """Human-readable action label with backfill detail."""

    base: str = _ACTION_LABELS.get(entry.action, str(entry.action))
    if entry.backfill.action == BackfillAction.BOUNDED and entry.backfill.duration is not None:
        return f"bounded backfill ({entry.backfill.duration})"
    if entry.backfill.action == BackfillAction.FULL:
        return "full build"
    return base


def _policy_label(entry: ModelPlanEntry) -> str | None:
    """Format the policy that caused the action, if any."""

    if (
        entry.reason == PlanReason.QUERY_CHANGED
        and entry.backfill.action != BackfillAction.WARN_ONLY
    ):
        duration: str = entry.backfill.duration or "full"
        return f"query_change_backfill={_backfill_value(entry.backfill.action, duration)}"
    if (
        entry.reason == PlanReason.SCHEMA_CHANGED
        and entry.backfill.action != BackfillAction.WARN_ONLY
    ):
        duration = entry.backfill.duration or "full"
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
        line: str = f"    {symbol} {finding.column_name}{type_info}   ({kind_label})"
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
        formatted: str = f"    {stripped}"
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
