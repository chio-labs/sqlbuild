"""Audit plan entry construction."""

from __future__ import annotations

import re

from sqlbuild.compiler.compile.models import (
    CompiledAudit,
    CompiledRelationTarget,
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

    return AuditPlanEntry(
        key=audit.key,
        name=audit.name,
        resolved_sql=resolved_sql,
        scope_deps=audit.scope_deps,
        attached_target_name=audit.attached_target_name,
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
