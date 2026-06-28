"""Audit SQL rendering with optional relation overrides."""

from __future__ import annotations

import re

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.constants import REF_PATTERN, SEED_PATTERN, SOURCE_PATTERN
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.spec.models.source import SourceEntry


def render_audit_sql(
    *,
    unresolved_sql: str,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    adapter: BaseAdapter | None = None,
    relation_overrides: dict[str, str] | None = None,
) -> str:
    """Render audit SQL from unresolved markers with optional relation overrides."""

    effective_overrides: dict[str, str] = (
        relation_overrides if relation_overrides is not None else {}
    )
    resolved: str = _render_refs(
        sql=unresolved_sql,
        model_locations=model_locations,
        seed_locations=seed_locations,
        relation_overrides=effective_overrides,
    )
    resolved = _render_sources(
        sql=resolved,
        source_map=source_map,
        adapter=adapter,
    )
    return resolved


def _render_refs(
    *,
    sql: str,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    relation_overrides: dict[str, str],
) -> str:
    """Replace __ref() calls using overrides first, then normal targets."""

    def _replace_ref(match: re.Match[str]) -> str:
        ref_name: str = match.group(1)
        override: str | None = relation_overrides.get(ref_name)
        if override is not None:
            return override
        target: CompiledRelationLocation | None = model_locations.get(ref_name)
        if target is None:
            target = seed_locations.get(ref_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    def _replace_seed(match: re.Match[str]) -> str:
        seed_name: str = match.group(1)
        target: CompiledRelationLocation | None = seed_locations.get(seed_name)
        if target is None or target.qualified_name is None:
            return match.group(0)
        return target.qualified_name

    resolved: str = REF_PATTERN.sub(_replace_ref, sql)
    return SEED_PATTERN.sub(_replace_seed, resolved)


def _render_sources(
    *,
    sql: str,
    source_map: dict[str, SourceEntry],
    adapter: BaseAdapter | None,
) -> str:
    """Replace __source() calls with qualified source names."""

    def _replace(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        entry: SourceEntry | None = source_map.get(source_name)
        if entry is None:
            return match.group(0)
        return render_source_relation(entry, adapter=adapter)

    return SOURCE_PATTERN.sub(_replace, sql)
