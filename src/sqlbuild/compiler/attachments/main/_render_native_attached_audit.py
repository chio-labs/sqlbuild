"""Render one attached generic audit natively."""

from __future__ import annotations

from dataclasses import asdict

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.models import NativeAuditPolicies, NativeRenderedAudit


def render_native_attached_audit(
    *,
    labels: tuple[str, str],
    sql_body: str,
    evidence_sql: str | None,
    implicit_arguments: dict[str, str],
    explicit_arguments: dict[str, object],
    policies: NativeAuditPolicies,
) -> NativeRenderedAudit:
    """Return the rendering of `(owner, audit)`, or its render and policy errors."""

    return NativeRenderedAudit(
        *_native.render_attached_generic_audit(
            labels,
            (sql_body, evidence_sql),
            (list(implicit_arguments.items()), explicit_arguments),
            asdict(policies),
        )
    )
