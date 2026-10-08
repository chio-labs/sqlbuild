"""Plain values exchanged with the native compile attachments."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NativeAuditPolicies:
    """One attachment's evaluation mode, threshold facts, severities and run scopes."""

    measurement: bool
    has_thresholds: bool
    has_minimum_samples: bool
    threshold_error: bool
    instance_severity: str | None
    default_severity: str | None
    instance_run_scope: str | None
    default_run_scope: str | None


@dataclass(frozen=True, slots=True)
class NativeRenderedAudit:
    """Rendered audit SQL, the severity value and where the run scope comes from."""

    sql_body: str
    evidence_sql: str | None
    severity: str
    run_scope_source: str
