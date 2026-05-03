"""Audit plan entry construction."""

from __future__ import annotations

import re

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
from sqlbuild.spec.models.source import SourceEntry

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
_SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')


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

    resolved_sql: str = _resolve_audit_refs(
        sql=audit.sql_body,
        model_targets=model_targets,
        seed_targets=seed_targets,
    )
    resolved_sql = _resolve_audit_sources(
        sql=resolved_sql,
        source_map=source_map,
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


def _resolve_audit_refs(
    *,
    sql: str,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
) -> str:
    """Replace __ref() calls in audit SQL with qualified names."""

    def _replace(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        target: CompiledRelationTarget | None = model_targets.get(ref_name)
        if target is None:
            target = seed_targets.get(ref_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    return _REF_PATTERN.sub(_replace, sql)


def _resolve_audit_sources(
    *,
    sql: str,
    source_map: dict[str, SourceEntry],
) -> str:
    """Replace __source() calls in audit SQL with qualified names."""

    def _replace(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        entry: SourceEntry | None = source_map.get(source_name)
        if entry is None:
            return match.group(0)
        parts: list[str] = []
        if entry.database is not None:
            parts.append(entry.database)
        if entry.schema is not None:
            parts.append(entry.schema)
        table_name: str = entry.table if entry.table is not None else entry.name
        parts.append(table_name)
        return ".".join(parts)

    return _SOURCE_PATTERN.sub(_replace, sql)
