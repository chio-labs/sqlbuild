"""Audit plan entry construction."""

from __future__ import annotations

from sqlbuild.compiler.auditing.main.render import render_audit_sql
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.planner.helpers.audit_scheduling import (
    resolve_attachment_kind,
    resolve_effective_run_scope,
)
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.shared.helpers.sql_resolution import assert_no_unresolved_sql_markers
from sqlbuild.spec.models.source import SourceEntry


def plan_audit(
    *,
    audit: CompiledAudit,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    model_materializations: dict[str, str],
) -> AuditPlanEntry:
    """Build an audit plan entry with refs and sources resolved."""

    resolved_sql: str = render_audit_sql(
        unresolved_sql=audit.sql_body,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
    )
    assert_no_unresolved_sql_markers(
        sql=resolved_sql,
        context=f"audit '{audit.name}' planned SQL",
    )

    attachment_kind: AuditAttachmentKind
    attached_target_name: str | None
    attachment_kind, attached_target_name = resolve_attachment_kind(
        audit=audit,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
    )

    attached_materialization: str | None = None
    if attachment_kind == AuditAttachmentKind.MODEL and attached_target_name is not None:
        attached_materialization = model_materializations.get(attached_target_name)

    requested_run_scope: AuditRunScope = AuditRunScope(
        audit.run_scope if audit.run_scope is not None else AuditRunScope.FINAL
    )
    severity: AuditSeverity = AuditSeverity(
        audit.severity if audit.severity is not None else AuditSeverity.WARN
    )

    effective_run_scope: AuditRunScope = resolve_effective_run_scope(
        requested_run_scope=requested_run_scope,
        attached_model_materialization=attached_materialization,
    )

    return AuditPlanEntry(
        key=audit.key,
        name=audit.name,
        resolved_sql=resolved_sql,
        unresolved_sql=audit.sql_body,
        attachment_kind=attachment_kind,
        severity=severity,
        requested_run_scope=requested_run_scope,
        effective_run_scope=effective_run_scope,
        scope_deps=audit.scope_deps,
        attached_target_name=attached_target_name,
        attached_column_name=audit.attached_column_name,
    )
