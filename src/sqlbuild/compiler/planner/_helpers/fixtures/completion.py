"""Schema-aware completion for test-only relation fixtures."""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from sqlbuild._native import (
    analyze_resolved_column_reads,
)
from sqlbuild._native import (
    build_relation_fixture_completion as _native_fixture_completion,
)
from sqlbuild._native import (
    build_relation_fixture_context as build_relation_fixture_context,
)
from sqlbuild._native import (
    complete_empty_fixture_sql as complete_empty_fixture_sql,
)
from sqlbuild._native import (
    complete_typed_null_columns as complete_typed_null_columns,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    DynamicColumnContractProof,
)
from sqlbuild.compiler.compile.types import (
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
)
from sqlbuild.compiler.planner.models import (
    FixtureRelationMetadata,
    RelationFixtureCompletion,
    RelationFixturePlanningContext,
)
from sqlbuild.compiler.planner.types import FixtureGroups, FixtureKey
from sqlbuild.compiler.references.constants import REF_PATTERN, SEED_PATTERN, SOURCE_PATTERN
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_DBT_REF_PATTERN: re.Pattern[str] = re.compile(r'__dbt_ref\("([^"]+)"\s*,\s*"([^"]+)"\)')


def build_relation_fixture_completion(
    *,
    project: CompiledProjectView,
    adapter: BaseAdapter,
    ordered_model_names: tuple[str, ...],
    fixture_groups: FixtureGroups,
    planning_context: RelationFixturePlanningContext | None = None,
) -> RelationFixtureCompletion:
    """Complete required omitted columns with typed nulls unless explicitly non-nullable."""

    return _native_fixture_completion(
        project=project,
        adapter=adapter,
        request=(ordered_model_names, fixture_groups),
        planning_context=planning_context,
    )


def _required_fixture_columns(
    *,
    ordered_model_names: tuple[str, ...],
    model_map: dict[str, CompiledModelView],
    fixture_keys: frozenset[FixtureKey],
    relations: dict[FixtureKey, FixtureRelationMetadata],
    authoritative_columns: dict[FixtureKey, frozenset[str]],
    adapter: BaseAdapter,
) -> tuple[dict[FixtureKey, dict[str, set[str]]], frozenset[FixtureKey]]:
    required: dict[FixtureKey, dict[str, set[str]]] = {}
    star_fixture_keys: set[FixtureKey] = set()
    dialect: str | None = adapter.expression_inference_profile().sql_analysis_dialect
    for model_name in ordered_model_names:
        model: CompiledModelView | None = model_map.get(model_name)
        if model is None:
            continue
        for upstream in _resolved_fixture_reads(
            query_sql=model.query_sql,
            references=model.references,
            fast_lineage=model.fast_lineage_columns or (),
            fixture_keys=fixture_keys,
            dialect=dialect,
        ):
            key: FixtureKey = (
                CompiledResourceType(upstream.resource_type),
                upstream.resource_name,
            )
            if key not in fixture_keys:
                continue
            if (
                key in authoritative_columns
                and upstream.column_name.casefold() not in authoritative_columns[key]
            ):
                continue
            required.setdefault(key, {}).setdefault(upstream.column_name, set()).add(model_name)
        if model.fast_lineage_has_star:
            model_star_fixture_keys: frozenset[FixtureKey] = _star_fixture_keys(
                model=model,
                fixture_keys=fixture_keys,
                relations=relations,
                adapter=adapter,
            )
            star_fixture_keys.update(model_star_fixture_keys)
            for key in model_star_fixture_keys:
                relation: FixtureRelationMetadata | None = relations.get(key)
                if relation is None or not relation.authoritative_names:
                    continue
                for column in relation.columns:
                    required.setdefault(key, {}).setdefault(column.name, set()).add(model_name)
    return required, frozenset(star_fixture_keys)


def _resolved_fixture_reads(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...],
    fast_lineage: Sequence[CompiledLineageColumnFact],
    fixture_keys: frozenset[FixtureKey],
    dialect: str | None,
) -> tuple[CompiledLineageSourceFact, ...]:
    """Return external model reads without treating fallback lineage as authoritative."""

    high_confidence_reads: list[CompiledLineageSourceFact] = []
    for fact in fast_lineage:
        if fact.confidence == ColumnLineageConfidence.HIGH:
            high_confidence_reads.extend(fact.upstream_columns)
    needs_resolution: bool = any(
        _reference_fixture_key(reference) in fixture_keys for reference in references
    )
    if not needs_resolution:
        return tuple(high_confidence_reads)
    resolved: tuple[CompiledLineageSourceFact, ...] = _cached_resolved_column_reads(
        query_sql=query_sql,
        references=references,
        dialect=dialect,
    )
    return tuple(dict.fromkeys([*high_confidence_reads, *resolved]))


def _reference_fixture_key(reference: CompileSqlReference) -> FixtureKey | None:
    resource_type: CompiledResourceType | None = {
        SqlReferenceKind.REF: CompiledResourceType.MODEL,
        SqlReferenceKind.SOURCE: CompiledResourceType.SOURCE,
        SqlReferenceKind.SEED: CompiledResourceType.SEED,
    }.get(SqlReferenceKind(reference.ref_kind))
    return (resource_type, reference.ref_name) if resource_type is not None else None


@lru_cache(maxsize=4096)
def _cached_resolved_column_reads(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...],
    dialect: str | None,
) -> tuple[CompiledLineageSourceFact, ...]:
    return analyze_resolved_column_reads(
        query_sql=query_sql,
        references=references,
        dialect=dialect,
    )


def _star_fixture_keys(
    *,
    model: CompiledModelView,
    fixture_keys: frozenset[FixtureKey],
    relations: dict[FixtureKey, FixtureRelationMetadata],
    adapter: BaseAdapter,
) -> frozenset[FixtureKey]:
    dependency_keys: frozenset[FixtureKey] = frozenset(
        (CompiledResourceType(dependency.resource_type), dependency.name)
        for dependency in model.deps
        if (CompiledResourceType(dependency.resource_type), dependency.name) in fixture_keys
    )
    dynamic_contract: DynamicColumnContractProof | None = model.dynamic_column_contract
    if dynamic_contract is not None and dynamic_contract.output_proven:
        input_relations: frozenset[str] = frozenset(
            name.casefold() for name in dynamic_contract.input_relations
        )
        return frozenset(key for key in dependency_keys if key[1].casefold() in input_relations)
    schema_tables: list[dict[str, object]] = []
    for key in dependency_keys:
        relation: FixtureRelationMetadata | None = relations.get(key)
        if relation is None or not relation.columns:
            continue
        schema_tables.append(
            {
                "name": key[1],
                "columns": [
                    {"name": column.name, "type": column.type or "UNKNOWN"}
                    for column in relation.columns
                ],
            }
        )
    if not schema_tables:
        return frozenset()
    polyglot_module: Any = import_polyglot_sql()
    try:
        analysis: object = polyglot_module.analyze_query(
            _replace_relation_markers_with_stubs(model.query_sql),
            {
                "dialect": adapter.expression_inference_profile().sql_analysis_dialect or "generic",
                "schema": {"tables": schema_tables},
            },
        )
    except polyglot_module.PolyglotError:
        return frozenset()
    if not isinstance(analysis, dict):
        return frozenset()
    star_projections: object = analysis.get("starProjections")
    query_relations: object = analysis.get("relations")
    if not isinstance(star_projections, list) or not isinstance(query_relations, list):
        return frozenset()
    relation_names_by_alias: dict[str, str] = {}
    for query_relation in query_relations:
        if not isinstance(query_relation, dict):
            continue
        name: object = query_relation.get("name")
        alias: object = query_relation.get("alias")
        if not isinstance(name, str):
            continue
        relation_names_by_alias[name.casefold()] = name.casefold()
        if isinstance(alias, str):
            relation_names_by_alias[alias.casefold()] = name.casefold()
    star_relation_names: set[str] = set()
    for projection in star_projections:
        if not isinstance(projection, dict):
            continue
        table: object = projection.get("table")
        if table is None:
            expanded_columns: object = projection.get("expandedColumns")
            if not isinstance(expanded_columns, list):
                continue
            expanded_names: set[str] = {
                column.casefold() for column in expanded_columns if isinstance(column, str)
            }
            for key in dependency_keys:
                relation: FixtureRelationMetadata | None = relations.get(key)
                if relation is not None and any(
                    column.name.casefold() in expanded_names for column in relation.columns
                ):
                    star_relation_names.add(key[1].casefold())
        elif isinstance(table, str):
            relation_name: str | None = relation_names_by_alias.get(table.casefold())
            if relation_name is not None:
                star_relation_names.add(relation_name)
    return frozenset(key for key in dependency_keys if key[1].casefold() in star_relation_names)


def _replace_relation_markers_with_stubs(query_sql: str) -> str:
    result: str = REF_PATTERN.sub(r"\1", query_sql)
    result = SEED_PATTERN.sub(r"\1", result)
    result = SOURCE_PATTERN.sub(r"\1", result)
    return _DBT_REF_PATTERN.sub(r"\2", result)
