"""Schema-aware completion for test-only relation fixtures."""

from __future__ import annotations

import re
from collections import ChainMap
from collections.abc import Mapping, Sequence
from functools import lru_cache
from typing import Any

from sqlbuild._native import (
    analyze_resolved_column_reads,
)
from sqlbuild._native import (
    build_relation_fixture_completion as _native_fixture_completion,
)
from sqlbuild._native import (
    complete_empty_fixture_sql as complete_empty_fixture_sql,
)
from sqlbuild._native import (
    complete_typed_null_columns as complete_typed_null_columns,
)
from sqlbuild._native import (
    model_fixture_metadata as _model_fixture_metadata,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    DynamicColumnContractProof,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import (
    CompiledModelView,
    CompiledProjectView,
    CompiledResourceType,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
)
from sqlbuild.compiler.planner.models import (
    FixtureColumnMetadata,
    FixtureRelationMetadata,
    RelationFixtureCompletion,
    RelationFixtureDiagnostic,
    RelationFixturePlanningContext,
)
from sqlbuild.compiler.planner.types import ContractPolicy, FixtureGroups, FixtureKey
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


def _fixture_keys_requiring_analysis(
    *,
    inferred_by_fixture: dict[FixtureKey, tuple[InferredColumn, ...]],
    authoritative_columns: dict[FixtureKey, frozenset[str]],
) -> frozenset[FixtureKey]:
    required: set[FixtureKey] = set()
    for key, inferred in inferred_by_fixture.items():
        expected_names: frozenset[str] | None = authoritative_columns.get(key)
        supplied_names: frozenset[str] = frozenset(column.name.casefold() for column in inferred)
        if expected_names is None or not expected_names.issubset(supplied_names):
            required.add(key)
    return frozenset(required)


def build_relation_fixture_context(
    *,
    project: CompiledProjectView,
    models_by_name: dict[str, CompiledModelView] | None = None,
) -> RelationFixturePlanningContext:
    """Build immutable project-wide fixture metadata once per planning invocation."""

    model_map: dict[str, CompiledModelView] = (
        {model.name: model for model in project.models}
        if models_by_name is None
        else models_by_name
    )
    relations: dict[FixtureKey, FixtureRelationMetadata] = _fixture_relation_metadata(
        project=project,
        model_map=model_map,
    )
    authoritative_columns: dict[FixtureKey, frozenset[str]] = _authoritative_fixture_columns(
        relations=relations
    )
    return RelationFixturePlanningContext(
        models_by_name=model_map,
        relations=relations,
        authoritative_columns=authoritative_columns,
        expected_types=_base_expected_fixture_types(relations=relations),
    )


def _authoritative_fixture_columns(
    *, relations: dict[FixtureKey, FixtureRelationMetadata]
) -> dict[FixtureKey, frozenset[str]]:
    authoritative: dict[FixtureKey, frozenset[str]] = {}
    for key, relation in relations.items():
        if relation.authoritative_names:
            authoritative[key] = frozenset(column.name.casefold() for column in relation.columns)
    return authoritative


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


def _fixture_relation_metadata(
    *, project: CompiledProjectView, model_map: dict[str, CompiledModelView]
) -> dict[FixtureKey, FixtureRelationMetadata]:
    relations: dict[FixtureKey, FixtureRelationMetadata] = {}
    for model_name, model in model_map.items():
        relations[(CompiledResourceType.MODEL, model_name)] = _model_fixture_metadata(model=model)
    for source in project.sources:
        relations[(CompiledResourceType.SOURCE, source.name)] = FixtureRelationMetadata(
            columns=tuple(
                FixtureColumnMetadata(
                    name=column.name,
                    type=column.type,
                    nullable=column.nullable,
                )
                for column in source.source_entry.columns
            ),
            authoritative_names=source.source_entry.contract == ContractPolicy.ENFORCED,
        )
    for seed in project.seeds:
        seed_columns: tuple[FixtureColumnMetadata, ...] = tuple(
            FixtureColumnMetadata(
                name=column.name,
                type=column.type,
                nullable=column.nullable,
            )
            for column in seed.schema_entry.columns
        )
        relations[(CompiledResourceType.SEED, seed.name)] = FixtureRelationMetadata(
            columns=seed_columns,
            authoritative_names=bool(seed_columns),
        )
    return relations


def _expected_fixture_types(
    *,
    base_expected_types: dict[FixtureKey, dict[str, str]],
    ordered_model_names: tuple[str, ...],
    model_map: dict[str, CompiledModelView],
) -> Mapping[FixtureKey, dict[str, str]]:
    expected_types: ChainMap[FixtureKey, dict[str, str]] = ChainMap({}, base_expected_types)
    for model_name in ordered_model_names:
        model: CompiledModelView | None = model_map.get(model_name)
        if model is None:
            continue
        model_key: FixtureKey = (CompiledResourceType.MODEL, model_name)
        model_types: dict[str, str] = dict(expected_types[model_key])
        expected_types[model_key] = model_types
        for lineage_column in model.fast_lineage_columns or ():
            if lineage_column.transform_kind != ColumnTransformKind.DIRECT:
                continue
            upstream_types: set[str] = set()
            for upstream in lineage_column.upstream_columns:
                upstream_type: str | None = expected_types.get(
                    (CompiledResourceType(upstream.resource_type), upstream.resource_name), {}
                ).get(upstream.column_name.casefold())
                if upstream_type is not None:
                    upstream_types.add(upstream_type)
            if len(upstream_types) == 1:
                model_types.setdefault(
                    lineage_column.output_column.casefold(), upstream_types.pop()
                )
    return expected_types


def _base_expected_fixture_types(
    *, relations: dict[FixtureKey, FixtureRelationMetadata]
) -> dict[FixtureKey, dict[str, str]]:
    expected_types: dict[FixtureKey, dict[str, str]] = {}
    for key, relation in relations.items():
        column_types: dict[str, str] = {}
        for column in relation.columns:
            if column.type is not None:
                column_types[column.name.casefold()] = column.type
        expected_types[key] = column_types
    return expected_types


def _unknown_fixture_column_diagnostics(
    *,
    inferred_by_fixture: dict[FixtureKey, tuple[InferredColumn, ...]],
    relations: dict[FixtureKey, FixtureRelationMetadata],
) -> tuple[RelationFixtureDiagnostic, ...]:
    diagnostics: list[RelationFixtureDiagnostic] = []
    for key, inferred in inferred_by_fixture.items():
        relation: FixtureRelationMetadata | None = relations.get(key)
        if relation is None or not relation.authoritative_names:
            continue
        expected_names: set[str] = {column.name.casefold() for column in relation.columns}
        unknown: tuple[str, ...] = tuple(
            sorted(
                column.name for column in inferred if column.name.casefold() not in expected_names
            )
        )
        if unknown:
            diagnostics.append(
                RelationFixtureDiagnostic(
                    key=key,
                    message=(
                        f"mock {key[0].value} '{key[1]}' supplies unknown columns: "
                        f"{', '.join(unknown)}"
                    ),
                )
            )
    return tuple(diagnostics)
