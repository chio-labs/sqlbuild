"""Render one attached generic audit natively for the preview compiler engine."""

from __future__ import annotations

from dataclasses import asdict

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.models import NativeAuditPolicies, NativeRenderedAudit


def render_native_attached_audit(
    *,
    labels: tuple[str, str],
    sql_body: str,
    evidence_sql: str | None,
    implicit_arguments: dict[str, object],
    explicit_arguments: dict[str, object],
    policies: NativeAuditPolicies,
) -> NativeRenderedAudit | None:
    """Return the rendering with Python's errors for `(owner, audit)`, or None for Python."""

    if not all(
        value is None or isinstance(value, str)
        for value in (
            policies.instance_severity,
            policies.default_severity,
            policies.instance_run_scope,
            policies.default_run_scope,
        )
    ) or not isinstance(explicit_arguments, dict):
        return None
    rendered: tuple[str | None, str, str | None, str, str, str | None] | None = (
        _native.render_attached_generic_audit(
            labels,
            (sql_body, evidence_sql),
            (implicit_arguments, explicit_arguments),
            asdict(policies),
        )
    )
    return None if rendered is None else NativeRenderedAudit(*rendered)
