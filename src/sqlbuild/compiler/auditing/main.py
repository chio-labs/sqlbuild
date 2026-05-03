"""Audit SQL rendering with optional relation overrides."""

from __future__ import annotations

import re

from sqlbuild.compiler.auditing.constants import REF_PATTERN, SOURCE_PATTERN
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.spec.models.source import SourceEntry


def render_audit_sql(
    *,
    unresolved_sql: str,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    relation_overrides: dict[str, str] | None = None,
) -> str:
    """Render audit SQL from unresolved markers with optional relation overrides.

    Relation overrides take precedence for specific ref names. All other refs
    and sources resolve normally through model/seed targets and source map.
    """

    effective_overrides: dict[str, str] = (
        relation_overrides if relation_overrides is not None else {}
    )
    resolved: str = _render_refs(
        sql=unresolved_sql,
        model_targets=model_targets,
        seed_targets=seed_targets,
        relation_overrides=effective_overrides,
    )
    resolved = _render_sources(
        sql=resolved,
        source_map=source_map,
    )
    return resolved


def _render_refs(
    *,
    sql: str,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    relation_overrides: dict[str, str],
) -> str:
    """Replace __ref() calls using overrides first, then normal targets."""

    def _replace(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        override: str | None = relation_overrides.get(ref_name)
        if override is not None:
            return override
        target: CompiledRelationTarget | None = model_targets.get(ref_name)
        if target is None:
            target = seed_targets.get(ref_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    return REF_PATTERN.sub(_replace, sql)


def _render_sources(
    *,
    sql: str,
    source_map: dict[str, SourceEntry],
) -> str:
    """Replace __source() calls with qualified source names."""

    def _replace(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        entry: SourceEntry | None = source_map.get(source_name)
        if entry is None:
            return match.group(0)
        return render_source_relation(entry)

    return SOURCE_PATTERN.sub(_replace, sql)
