"""Backfill policy resolution from model config and change detection results."""

from __future__ import annotations

import re

from sqlbuild.compiler.planner.models import BackfillResult, SchemaFinding
from sqlbuild.compiler.planner.types import BackfillAction, SchemaChangeKind

_BOUNDED_PATTERN: re.Pattern[str] = re.compile(r"^bounded\((.+)\)$")

_ACTION_PRIORITY: dict[BackfillAction, int] = {
    BackfillAction.WARN_ONLY: 0,
    BackfillAction.BOUNDED: 1,
    BackfillAction.FULL: 2,
}


def resolve_query_change_backfill(
    *,
    query_change_backfill: str | None,
) -> BackfillResult:
    """Resolve the backfill action for a detected query change."""

    return _resolve_backfill_value(query_change_backfill)


def resolve_schema_change_backfill(
    *,
    schema_change_backfill: dict[str, str],
    findings: tuple[SchemaFinding, ...],
) -> BackfillResult:
    """Resolve the most aggressive backfill action across schema change findings."""

    result: BackfillResult = BackfillResult(action=BackfillAction.WARN_ONLY)
    finding: SchemaFinding
    for finding in findings:
        policy_key: str | None = _finding_to_policy_key(finding)
        raw_value: str | None = schema_change_backfill.get(policy_key) if policy_key else None
        candidate: BackfillResult = _resolve_backfill_value(raw_value)
        result = pick_more_aggressive(result, candidate)
    return result


def pick_more_aggressive(a: BackfillResult, b: BackfillResult) -> BackfillResult:
    """Return the more aggressive of two backfill results."""

    if _ACTION_PRIORITY[a.action] >= _ACTION_PRIORITY[b.action]:
        return a
    return b


def _resolve_backfill_value(raw: str | None) -> BackfillResult:
    """Parse a raw backfill policy value into a BackfillResult."""

    if raw is None:
        return BackfillResult(action=BackfillAction.WARN_ONLY)
    if raw == BackfillAction.FULL:
        return BackfillResult(action=BackfillAction.FULL)
    match: re.Match[str] | None = _BOUNDED_PATTERN.match(raw)
    if match is not None:
        duration: str = match.group(1).strip()
        return BackfillResult(action=BackfillAction.BOUNDED, duration=duration)
    return BackfillResult(action=BackfillAction.WARN_ONLY)


def _finding_to_policy_key(finding: SchemaFinding) -> str | None:
    """Map a schema finding kind to the corresponding policy config key."""

    if finding.kind == SchemaChangeKind.COLUMN_ADDED:
        return "add_column"
    if finding.kind == SchemaChangeKind.COLUMN_TYPE_CHANGED:
        return "type_change"
    return None
