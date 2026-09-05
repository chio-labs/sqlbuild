"""Audit plan entry construction."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.main.render import render_audit_sql
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind
from sqlbuild.compiler.planner._helpers.output.audit_scheduling import (
    resolve_attachment_kind,
    resolve_effective_run_scope,
)
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.compiler.references.main.assert_no_unresolved_sql_markers import (
    assert_no_unresolved_sql_markers,
)
from sqlbuild.spec.contracts.models import SourceEntry


def plan_audit(
    *,
    audit: CompiledAudit,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    adapter: BaseAdapter,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    model_materializations: dict[str, str],
) -> AuditPlanEntry:
    """Build an audit plan entry with refs and sources resolved."""

    resolved_sql: str = render_audit_sql(
        unresolved_sql=audit.sql_body,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
        adapter=adapter,
    )
    assert_no_unresolved_sql_markers(
        sql=resolved_sql,
        context=f"audit '{audit.name}' planned SQL",
    )
    evidence_resolved_sql: str | None = None
    if audit.evidence_sql is not None:
        evidence_resolved_sql = render_audit_sql(
            unresolved_sql=audit.evidence_sql,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            adapter=adapter,
        )
        assert_no_unresolved_sql_markers(
            sql=evidence_resolved_sql,
            context=f"audit '{audit.name}' planned evidence SQL",
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
    attached_target_kind: AttachedAuditTargetKind | None = audit.attached_target_kind
    if attached_target_kind is None and attachment_kind == AuditAttachmentKind.MODEL:
        attached_target_kind = AttachedAuditTargetKind.MODEL
    elif attached_target_kind is None and attachment_kind == AuditAttachmentKind.SOURCE:
        attached_target_kind = AttachedAuditTargetKind.SOURCE

    return AuditPlanEntry(
        key=audit.key,
        name=audit.name,
        resolved_sql=resolved_sql,
        unresolved_sql=audit.sql_body,
        attachment_kind=attachment_kind,
        severity=severity,
        requested_run_scope=requested_run_scope,
        effective_run_scope=effective_run_scope,
        evaluation_mode=audit.evaluation_mode,
        value_column=(
            None
            if audit.measurement_contract is None
            else audit.measurement_contract.value_column
        ),
        sample_count_column=(
            None
            if audit.measurement_contract is None
            else audit.measurement_contract.sample_count_column
        ),
        sample_unit=(
            None if audit.measurement_contract is None else audit.measurement_contract.sample_unit
        ),
        thresholds=audit.thresholds,
        minimum_samples=audit.minimum_samples,
        evidence_resolved_sql=evidence_resolved_sql,
        evidence_unresolved_sql=audit.evidence_sql,
        evidence_limit=audit.evidence_limit,
        scope_deps=audit.scope_deps,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        attached_column_name=audit.attached_column_name,
        always_run=audit.always_run,
    )
