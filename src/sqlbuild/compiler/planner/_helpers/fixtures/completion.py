"""Schema-aware completion for test-only relation fixtures."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.main._analyze_columns_and_lineage import (
    analyze_resolved_column_reads,
)
from sqlbuild.compiler.compile.main._infer_fixture_columns import infer_fixture_column_facts
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompiledModel,
    CompiledProject,
    CompileSqlReference,
    DynamicColumnContractProof,
    FixtureColumnInference,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
)
from sqlbuild.compiler.planner._helpers.fixtures.empty_fixture import is_empty_fixture_query
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

_PARTIAL_FIXTURE_ALIAS: str = "__sqlbuild_partial_fixture"
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(r'__dbt_ref\("([^"]+)",\s*"([^"]+)"\)')


def build_relation_fixture_completion(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    ordered_model_names: tuple[str, ...],
    fixture_groups: FixtureGroups,
    planning_context: RelationFixturePlanningContext | None = None,
) -> RelationFixtureCompletion:
    """Complete required omitted columns with typed nulls unless explicitly non-nullable."""

    context: RelationFixturePlanningContext = planning_context or build_relation_fixture_context(
        project=project
    )
    model_map: dict[str, CompiledModel] = context.models_by_name
    relations: dict[FixtureKey, FixtureRelationMetadata] = context.relations
    fixture_sql_by_key: dict[FixtureKey, str]
    inferred_by_fixture: dict[FixtureKey, tuple[InferredColumn, ...]]
    null_literal_names_by_fixture: dict[FixtureKey, frozenset[str]]
    quoted_names_by_fixture: dict[FixtureKey, frozenset[str]]
    diagnostics: list[RelationFixtureDiagnostic]
    (
        fixture_sql_by_key,
        inferred_by_fixture,
        null_literal_names_by_fixture,
        quoted_names_by_fixture,
        diagnostics,
    ) = _prepare_fixture_inputs(
        fixture_groups=fixture_groups,
        relations=relations,
        adapter=adapter,
    )

    fixture_keys_requiring_analysis: frozenset[FixtureKey] = _fixture_keys_requiring_analysis(
        inferred_by_fixture=inferred_by_fixture,
        authoritative_columns=context.authoritative_columns,
    )
    required: dict[FixtureKey, dict[str, set[str]]]
    star_fixture_keys: frozenset[FixtureKey]
    required, star_fixture_keys = _required_fixture_columns(
        ordered_model_names=ordered_model_names,
        model_map=model_map,
        fixture_keys=fixture_keys_requiring_analysis,
        relations=relations,
        authoritative_columns=context.authoritative_columns,
        adapter=adapter,
    )
    expected_types: dict[FixtureKey, dict[str, str]] = _expected_fixture_types(
        base_expected_types=context.expected_types,
        ordered_model_names=ordered_model_names,
        model_map=model_map,
    )
    typed_nulls_by_fixture: dict[FixtureKey, dict[str, str]] = _typed_null_fixture_types(
        null_literal_names_by_fixture=null_literal_names_by_fixture,
        expected_types=expected_types,
    )
    diagnostics.extend(
        _unknown_fixture_column_diagnostics(
            inferred_by_fixture=inferred_by_fixture, relations=relations
        )
    )

    completed_keys: set[FixtureKey] = set()
    for key, required_columns in required.items():
        inferred: tuple[InferredColumn, ...] | None = inferred_by_fixture.get(key)
        if inferred is None:
            continue
        available_names: set[str] = {column.name.casefold() for column in inferred}
        missing: tuple[str, ...] = tuple(
            sorted(name for name in required_columns if name.casefold() not in available_names)
        )
        typed_nulls: dict[str, str] = typed_nulls_by_fixture.get(key, {})
        if not missing and not typed_nulls:
            continue
        relation: FixtureRelationMetadata | None = relations.get(key)
        metadata: tuple[FixtureColumnMetadata, ...] = (
            relation.columns if relation is not None else ()
        )
        metadata_by_name: dict[str, FixtureColumnMetadata] = {
            column.name.casefold(): column for column in metadata
        }
        nullable_columns: list[FixtureColumnMetadata] = []
        unknown: list[str] = []
        non_nullable: list[str] = []
        for name in missing:
            column: FixtureColumnMetadata | None = metadata_by_name.get(name.casefold())
            if column is None or column.type is None:
                unknown.append(name)
            elif column.nullable is False:
                non_nullable.append(name)
            else:
                nullable_columns.append(column)
        if unknown:
            read_by: tuple[str, ...] = _models_reading_columns(
                column_names=tuple(unknown),
                required_columns=required_columns,
            )
            diagnostics.append(
                RelationFixtureDiagnostic(
                    key=key,
                    message=(
                        f"mock {key[0].value} '{key[1]}' is missing required columns: "
                        f"{', '.join(unknown)}; provide explicit values because their types are "
                        f"not authoritative (read by: {', '.join(read_by)})"
                    ),
                )
            )
        if non_nullable:
            diagnostics.append(
                RelationFixtureDiagnostic(
                    key=key,
                    message=(
                        f"mock {key[0].value} '{key[1]}' must provide required non-nullable "
                        f"columns: {', '.join(non_nullable)}"
                    ),
                )
            )
        if unknown or non_nullable:
            continue
        if key in star_fixture_keys and not _supplied_columns_form_schema_prefix(
            inferred=inferred,
            metadata=metadata,
        ):
            diagnostics.append(
                RelationFixtureDiagnostic(
                    key=key,
                    message=(
                        f"mock {key[0].value} '{key[1]}' supplies columns out of authoritative "
                        "order for a SELECT * closure; provide the leading relation columns in "
                        "schema order"
                    ),
                )
            )
            continue
        metadata_order: dict[str, int] = {
            column.name.casefold(): index for index, column in enumerate(metadata)
        }
        nullable_columns.sort(key=lambda column: metadata_order[column.name.casefold()])
        fixture_sql_by_key[key] = _completed_fixture_sql(
            sql=fixture_sql_by_key[key],
            inferred=inferred,
            typed_nulls=typed_nulls,
            quoted_names=quoted_names_by_fixture.get(key, frozenset()),
            completed=tuple(nullable_columns),
            adapter=adapter,
        )
        completed_keys.add(key)

    for key, typed_nulls in typed_nulls_by_fixture.items():
        if key in completed_keys:
            continue
        inferred = inferred_by_fixture[key]
        fixture_sql_by_key[key] = _completed_fixture_sql(
            sql=fixture_sql_by_key[key],
            inferred=inferred,
            typed_nulls=typed_nulls,
            quoted_names=quoted_names_by_fixture.get(key, frozenset()),
            completed=(),
            adapter=adapter,
        )

    return RelationFixtureCompletion(
        fixture_sql_by_key=fixture_sql_by_key,
        inferred_by_fixture=inferred_by_fixture,
        expected_types=expected_types,
        diagnostics=tuple(diagnostics),
    )


def _prepare_fixture_inputs(
    *,
    fixture_groups: FixtureGroups,
    relations: dict[FixtureKey, FixtureRelationMetadata],
    adapter: BaseAdapter,
) -> tuple[
    dict[FixtureKey, str],
    dict[FixtureKey, tuple[InferredColumn, ...]],
    dict[FixtureKey, frozenset[str]],
    dict[FixtureKey, frozenset[str]],
    list[RelationFixtureDiagnostic],
]:
    fixture_sql_by_key: dict[FixtureKey, str] = {}
    inferred_by_fixture: dict[FixtureKey, tuple[InferredColumn, ...]] = {}
    null_literal_names_by_fixture: dict[FixtureKey, frozenset[str]] = {}
    quoted_names_by_fixture: dict[FixtureKey, frozenset[str]] = {}
    diagnostics: list[RelationFixtureDiagnostic] = []
    for resource_type, fixtures in fixture_groups:
        for name, sql in fixtures.items():
            key: FixtureKey = (resource_type, name)
            fixture_sql: str = sql
            if is_empty_fixture_query(fixture_sql):
                empty_sql, empty_error = complete_empty_fixture_sql(
                    sql=fixture_sql,
                    relation=relations.get(key),
                    adapter=adapter,
                )
                if empty_error is not None:
                    diagnostics.append(
                        RelationFixtureDiagnostic(
                            key=key,
                            message=f"mock {key[0].value} '{key[1]}' {empty_error}",
                        )
                    )
                    fixture_sql_by_key[key] = fixture_sql
                    continue
                fixture_sql = empty_sql
            fixture_sql_by_key[key] = fixture_sql
            inference: FixtureColumnInference | None = infer_fixture_column_facts(
                query_sql=fixture_sql,
                inference_profile=adapter.expression_inference_profile(),
            )
            if inference is not None:
                inferred_by_fixture[key] = inference.columns
                null_literal_names_by_fixture[key] = inference.null_literal_names
                quoted_names_by_fixture[key] = inference.quoted_names
    return (
        fixture_sql_by_key,
        inferred_by_fixture,
        null_literal_names_by_fixture,
        quoted_names_by_fixture,
        diagnostics,
    )


def complete_typed_null_columns(
    *,
    sql: str,
    inference: FixtureColumnInference,
    expected_types: dict[str, str],
    adapter: BaseAdapter,
) -> str:
    """Apply authoritative types to direct bare-NULL projections."""

    typed_nulls: dict[str, str] = {
        name: expected_types[name]
        for name in inference.null_literal_names
        if name in expected_types
    }
    if not typed_nulls:
        return sql
    return _completed_fixture_sql(
        sql=sql,
        inferred=inference.columns,
        typed_nulls=typed_nulls,
        quoted_names=inference.quoted_names,
        completed=(),
        adapter=adapter,
    )


def complete_empty_fixture_sql(
    *,
    sql: str,
    relation: FixtureRelationMetadata | None,
    adapter: BaseAdapter,
) -> tuple[str, str | None]:
    """Expand an empty-fixture marker from authoritative relation metadata."""

    if not is_empty_fixture_query(sql):
        return sql, None
    if relation is None or not relation.authoritative_names:
        return sql, "uses __empty_fixture() but its column schema is not authoritative"
    unknown_types: tuple[str, ...] = tuple(
        column.name for column in relation.columns if column.type is None
    )
    if unknown_types:
        return (
            sql,
            f"uses __empty_fixture() but columns have unknown types: {', '.join(unknown_types)}",
        )
    if not relation.columns:
        return sql, "uses __empty_fixture() but its schema has no columns"
    projections: str = ",\n  ".join(
        f"CAST(NULL AS {column.type}) AS {adapter.render_identifier(column.name)}"
        for column in relation.columns
    )
    return f"SELECT\n  {projections}\nWHERE FALSE", None


def _typed_null_fixture_types(
    *,
    null_literal_names_by_fixture: dict[FixtureKey, frozenset[str]],
    expected_types: dict[FixtureKey, dict[str, str]],
) -> dict[FixtureKey, dict[str, str]]:
    result: dict[FixtureKey, dict[str, str]] = {}
    for key, null_literal_names in null_literal_names_by_fixture.items():
        fixture_types: dict[str, str] = {}
        expected_fixture_types: dict[str, str] = expected_types.get(key, {})
        for name in null_literal_names:
            expected_type: str | None = expected_fixture_types.get(name)
            if expected_type is not None:
                fixture_types[name] = expected_type
        if fixture_types:
            result[key] = fixture_types
    return result


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
    project: CompiledProject,
    models_by_name: dict[str, CompiledModel] | None = None,
) -> RelationFixturePlanningContext:
    """Build immutable project-wide fixture metadata once per planning invocation."""

    model_map: dict[str, CompiledModel] = (
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
    model_map: dict[str, CompiledModel],
    fixture_keys: frozenset[FixtureKey],
    relations: dict[FixtureKey, FixtureRelationMetadata],
    authoritative_columns: dict[FixtureKey, frozenset[str]],
    adapter: BaseAdapter,
) -> tuple[dict[FixtureKey, dict[str, set[str]]], frozenset[FixtureKey]]:
    required: dict[FixtureKey, dict[str, set[str]]] = {}
    star_fixture_keys: set[FixtureKey] = set()
    dialect: str | None = adapter.expression_inference_profile().sql_analysis_dialect
    for model_name in ordered_model_names:
        model: CompiledModel | None = model_map.get(model_name)
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
    fast_lineage: tuple[CompiledLineageColumnFact, ...],
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
    model: CompiledModel,
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
    *, project: CompiledProject, model_map: dict[str, CompiledModel]
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


def _model_fixture_metadata(*, model: CompiledModel) -> FixtureRelationMetadata:
    columns_by_name: dict[str, FixtureColumnMetadata] = {}
    order: list[str] = []
    for column in model.inferred_columns or ():
        key: str = column.name.casefold()
        order.append(key)
        columns_by_name[key] = FixtureColumnMetadata(
            name=column.name,
            type=column.type,
            nullable=None,
        )
    for column in model.schema_entry.columns if model.schema_entry is not None else ():
        key = column.name.casefold()
        if key not in columns_by_name:
            order.append(key)
        inferred: FixtureColumnMetadata | None = columns_by_name.get(key)
        columns_by_name[key] = FixtureColumnMetadata(
            name=column.name,
            type=column.type or (inferred.type if inferred is not None else None),
            nullable=(
                column.nullable
                if column.nullable is not None
                else (inferred.nullable if inferred is not None else None)
            ),
        )
    return FixtureRelationMetadata(
        columns=tuple(columns_by_name[key] for key in order),
        authoritative_names=(
            not model.fast_lineage_has_star
            and (
                model.config.values.get("contract") == ContractPolicy.ENFORCED
                or model.inferred_columns is not None
            )
        ),
    )


def _expected_fixture_types(
    *,
    base_expected_types: dict[FixtureKey, dict[str, str]],
    ordered_model_names: tuple[str, ...],
    model_map: dict[str, CompiledModel],
) -> dict[FixtureKey, dict[str, str]]:
    expected_types: dict[FixtureKey, dict[str, str]] = dict(base_expected_types)
    for model_name in ordered_model_names:
        model: CompiledModel | None = model_map.get(model_name)
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


def _models_reading_columns(
    *, column_names: tuple[str, ...], required_columns: dict[str, set[str]]
) -> tuple[str, ...]:
    model_names: set[str] = set()
    for name in column_names:
        model_names.update(required_columns[name])
    return tuple(sorted(model_names))


def _supplied_columns_form_schema_prefix(
    *,
    inferred: tuple[InferredColumn, ...],
    metadata: tuple[FixtureColumnMetadata, ...],
) -> bool:
    supplied_names: tuple[str, ...] = tuple(column.name.casefold() for column in inferred)
    schema_prefix: tuple[str, ...] = tuple(
        column.name.casefold() for column in metadata[: len(supplied_names)]
    )
    return supplied_names == schema_prefix


def _completed_fixture_sql(
    *,
    sql: str,
    inferred: tuple[InferredColumn, ...],
    typed_nulls: dict[str, str],
    quoted_names: frozenset[str],
    completed: tuple[FixtureColumnMetadata, ...],
    adapter: BaseAdapter,
) -> str:
    alias: str = adapter.render_identifier(_PARTIAL_FIXTURE_ALIAS)
    projections: list[str]
    if typed_nulls:
        projections = []
        for supplied_column in inferred:
            rendered_name: str = (
                adapter.render_exact_identifier(supplied_column.name)
                if supplied_column.name.casefold() in quoted_names
                else supplied_column.name
            )
            source_expression: str = f"{alias}.{rendered_name}"
            expected_type: str | None = typed_nulls.get(supplied_column.name.casefold())
            projections.append(
                source_expression
                if expected_type is None
                else f"CAST({source_expression} AS {expected_type}) AS {rendered_name}"
            )
    else:
        projections = [f"{alias}.*"]
    for completed_column in completed:
        projections.append(
            f"CAST(NULL AS {completed_column.type}) AS "
            f"{adapter.render_identifier(completed_column.name)}"
        )
    projection_sql: str = ",\n  ".join(projections)
    return f"SELECT\n  {projection_sql}\nFROM (\n{sql}\n) AS {alias}"
