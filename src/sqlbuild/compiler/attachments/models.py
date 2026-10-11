"""Plain values exchanged with the native compile attachments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NativeAuditPolicies:
    """One attachment's threshold facts, severities and run scopes."""

    has_thresholds: bool
    threshold_error: bool
    instance_severity: str | None
    default_severity: str | None
    instance_run_scope: str | None
    default_run_scope: str | None


@dataclass(frozen=True, slots=True)
class NativeRenderedAudit:
    """Rendered audit SQL and policies, or the render error and the later policy error."""

    render_error: str | None
    sql_body: str
    evidence_sql: str | None
    severity: str
    run_scope_source: str
    policy_error: str | None
