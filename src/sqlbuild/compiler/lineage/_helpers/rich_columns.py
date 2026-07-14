"""Polyglot-backed rich column lineage analyzer."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.types import BuiltinAdapter, TypeDialect
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage._helpers.columns import (
    _build_schema_mapping,
    _build_star_lineage,
    _normalize_sqlbuild_refs,
)
from sqlbuild.compiler.lineage.constants import (
    POLYGLOT_RESOLVED_SOURCE_CONFIDENCE,
    STAR_COLUMN_NAME,
)
from sqlbuild.compiler.lineage.models import (
    ColumnLineage,
    ColumnLineageEdge,
    ColumnLineageSource,
    ModelColumnLineage,
    PhysicalResource,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
    PolyglotAnalysisDialect,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_IS_STAR,
    POLYGLOT_ANALYSIS_NAME,
    POLYGLOT_ANALYSIS_NULLABILITY,
    POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL,
    POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE,
    POLYGLOT_ANALYSIS_PROJECTIONS,
    POLYGLOT_ANALYSIS_SOURCE_ALIAS,
    POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE,
    POLYGLOT_ANALYSIS_SOURCE_NAME,
    POLYGLOT_ANALYSIS_STAR_PROJECTIONS,
    POLYGLOT_ANALYSIS_TABLE,
    POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION,
    POLYGLOT_ANALYSIS_TRANSFORM_CAST,
    POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT,
    POLYGLOT_ANALYSIS_TRANSFORM_DIRECT,
    POLYGLOT_ANALYSIS_TRANSFORM_KIND,
    POLYGLOT_ANALYSIS_UPSTREAM,
    POLYGLOT_PAYLOAD_COLUMN,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.lineage")
_POLYGLOT_DIALECT_ALIASES: dict[str, PolyglotAnalysisDialect] = {
    "": PolyglotAnalysisDialect.GENERIC,
    "ansi": PolyglotAnalysisDialect.GENERIC,
    "generic": PolyglotAnalysisDialect.GENERIC,
    TypeDialect.GENERIC.value: PolyglotAnalysisDialect.GENERIC,
    TypeDialect.BIGQUERY.value: PolyglotAnalysisDialect.BIGQUERY,
    TypeDialect.SNOWFLAKE.value: PolyglotAnalysisDialect.SNOWFLAKE,
    TypeDialect.DUCKDB.value: PolyglotAnalysisDialect.DUCKDB,
    TypeDialect.MOTHERDUCK.value: PolyglotAnalysisDialect.DUCKDB,
    TypeDialect.DATABRICKS.value: PolyglotAnalysisDialect.DATABRICKS,
    TypeDialect.POSTGRES.value: PolyglotAnalysisDialect.POSTGRESQL,
    TypeDialect.TSQL.value: PolyglotAnalysisDialect.TSQL,
    BuiltinAdapter.SQLSERVER.value: PolyglotAnalysisDialect.TSQL,
    "postgresql": PolyglotAnalysisDialect.POSTGRESQL,
}


def build_rich_project_column_lineage(
    *,
    project: CompiledProject,
    dialect: str | None = None,
    model_names: frozenset[str] | None = None,
) -> ProjectColumnLineage | None:
    """Build a rich project column lineage graph using Polyglot query analysis."""

    if not project.settings.sql_analysis:
        return None

    schema: dict[str, dict[str, str]] = _build_schema_mapping(project)
    model_results: dict[str, ModelColumnLineage] = {}
    collapsed_edges: list[ColumnLineageEdge] = []

    for model in project.models:
        if model_names is not None and model.name not in model_names:
            continue
        result: ModelColumnLineage | None = _build_polyglot_model_column_lineage(
            model=model,
            schema=schema,
            dialect=dialect,
        )
        if result is None:
            continue
        model_results[model.name] = result
        target_resource_name: str = model.name
        for column in result.columns:
            target: QualifiedLineageColumn = QualifiedLineageColumn(
                resource_type=CompiledResourceType.MODEL,
                resource_name=target_resource_name,
                column_name=column.output_column,
            )
            for upstream in column.upstream_columns:
                collapsed_edges.append(
                    ColumnLineageEdge(
                        source=upstream.as_qualified_column(),
                        target=target,
                        transform_kind=column.transform_kind,
                        confidence=column.confidence,
                    )
                )

    return ProjectColumnLineage(models=model_results, edges=tuple(collapsed_edges))


def _build_polyglot_model_column_lineage(
    *,
    model: CompiledModel,
    schema: dict[str, dict[str, str]],
    dialect: str | None,
) -> ModelColumnLineage | None:
    normalized_sql: str
    physical_resources: tuple[PhysicalResource, ...]
    normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
    resource_by_physical_name: dict[str, PhysicalResource] = {
        resource.physical_name: resource for resource in physical_resources
    }
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    try:
        analysis: Any = polyglot_module.analyze_query(
            normalized_sql,
            {
                "dialect": _polyglot_dialect(dialect),
                "schema": _polyglot_schema(schema),
            },
        )
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="rich column lineage analysis failed; skipping model",
            sqlbuild_model=model.name,
            sqlbuild_error=str(error),
        )
        return None
    if not isinstance(analysis, dict):
        return None
    projections: object = analysis.get(POLYGLOT_ANALYSIS_PROJECTIONS)
    if not isinstance(projections, list):
        return None

    lineages: list[ColumnLineage] = []
    star_expanded_columns: frozenset[str] = _star_expanded_columns(analysis)
    projection: object
    for projection in projections:
        if not isinstance(projection, dict):
            continue
        if bool(projection.get(POLYGLOT_ANALYSIS_IS_STAR)):
            continue
        output_value: object = projection.get(POLYGLOT_ANALYSIS_NAME)
        output_column: str = output_value if isinstance(output_value, str) else ""
        if not output_column:
            continue
        if output_column in star_expanded_columns:
            continue
        upstream_columns, confidence = _projection_upstreams(
            projection=projection,
            resource_by_physical_name=resource_by_physical_name,
        )
        transform_kind: ColumnTransformKind = _projection_transform_kind(
            projection=projection,
            has_upstream=bool(upstream_columns),
        )
        lineages.append(
            ColumnLineage(
                output_column=output_column,
                transform_kind=transform_kind,
                expression_sql=None,
                upstream_columns=upstream_columns,
                nullability=_projection_nullability(projection),
                confidence=(
                    confidence
                    if upstream_columns or transform_kind == ColumnTransformKind.CONSTANT
                    else ColumnLineageConfidence.UNKNOWN
                ),
            )
        )

    has_star: bool = bool(star_expanded_columns)
    if has_star:
        lineages.extend(
            _build_star_lineage(
                model=model,
                schema=schema,
                physical_resources=physical_resources,
                existing_columns={lineage.output_column for lineage in lineages},
            )
        )

    return ModelColumnLineage(
        model_name=model.name,
        columns=tuple(lineages),
        has_star=has_star,
    )


def _projection_upstreams(
    *,
    projection: dict[str, Any],
    resource_by_physical_name: dict[str, PhysicalResource],
) -> tuple[tuple[ColumnLineageSource, ...], ColumnLineageConfidence]:
    upstream_values: object = projection.get(POLYGLOT_ANALYSIS_UPSTREAM)
    if not isinstance(upstream_values, list):
        return (), ColumnLineageConfidence.UNKNOWN
    sources: list[ColumnLineageSource] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
    upstream: object
    for upstream in upstream_values:
        if not isinstance(upstream, dict):
            continue
        column_value: object = upstream.get(POLYGLOT_PAYLOAD_COLUMN)
        if (
            not isinstance(column_value, str)
            or not column_value
            or column_value == STAR_COLUMN_NAME
        ):
            continue
        source_name: object = upstream.get(POLYGLOT_ANALYSIS_SOURCE_NAME) or upstream.get(
            POLYGLOT_ANALYSIS_TABLE
        )
        if not isinstance(source_name, str) or not source_name:
            confidence = ColumnLineageConfidence.UNKNOWN
            continue
        resource: PhysicalResource | None = resource_by_physical_name.get(source_name)
        if resource is None:
            continue
        source_confidence: object = upstream.get(POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE)
        source_alias: object = upstream.get(POLYGLOT_ANALYSIS_SOURCE_ALIAS)
        if source_confidence != POLYGLOT_RESOLVED_SOURCE_CONFIDENCE and not isinstance(
            source_alias, str
        ):
            confidence = ColumnLineageConfidence.MEDIUM
        key: tuple[CompiledResourceType, str, str] = (
            resource.resource_type,
            resource.resource_name,
            column_value,
        )
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            ColumnLineageSource(
                resource_type=resource.resource_type,
                resource_name=resource.resource_name,
                column_name=column_value,
            )
        )
    return tuple(
        sorted(
            sources,
            key=lambda source: (
                source.resource_type.value,
                source.resource_name,
                source.column_name,
            ),
        )
    ), confidence


def _star_expanded_columns(analysis: dict[str, Any]) -> frozenset[str]:
    expanded: set[str] = set()
    star_projections: object = analysis.get(POLYGLOT_ANALYSIS_STAR_PROJECTIONS)
    if not isinstance(star_projections, list):
        return frozenset()
    star_projection: object
    for star_projection in star_projections:
        if not isinstance(star_projection, dict):
            continue
        columns: object = star_projection.get("expandedColumns")
        if not isinstance(columns, list):
            continue
        column: object
        for column in columns:
            if isinstance(column, str) and column:
                expanded.add(column)
    return frozenset(expanded)


def _polyglot_schema(schema: dict[str, dict[str, str]]) -> dict[str, object]:
    tables: list[dict[str, object]] = []
    for table_name, columns in sorted(schema.items()):
        table_columns: list[dict[str, str]] = []
        for column_name, column_type in sorted(columns.items()):
            table_columns.append({"name": column_name, "type": column_type or "UNKNOWN"})
        tables.append({"name": table_name, "columns": table_columns})
    return {"tables": tables}


def _polyglot_dialect(dialect: str | TypeDialect | None) -> PolyglotAnalysisDialect:
    if dialect is None:
        return PolyglotAnalysisDialect.GENERIC
    normalized: str = dialect.strip().lower()
    mapped: PolyglotAnalysisDialect | None = _POLYGLOT_DIALECT_ALIASES.get(normalized)
    if mapped is not None:
        return mapped
    return PolyglotAnalysisDialect(normalized)


def _projection_nullability(projection: dict[str, Any]) -> InferredNullability:
    value: object = projection.get(POLYGLOT_ANALYSIS_NULLABILITY)
    if value == POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL:
        return InferredNullability.NON_NULL
    if value == POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE:
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN


def _projection_transform_kind(
    *, projection: dict[str, Any], has_upstream: bool
) -> ColumnTransformKind:
    transform_kind: str = str(projection.get(POLYGLOT_ANALYSIS_TRANSFORM_KIND) or "")
    if transform_kind == POLYGLOT_ANALYSIS_TRANSFORM_CAST:
        return ColumnTransformKind.CAST
    if transform_kind == POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION:
        return ColumnTransformKind.AGGREGATION
    if transform_kind == POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT or not has_upstream:
        return ColumnTransformKind.CONSTANT
    if transform_kind == POLYGLOT_ANALYSIS_TRANSFORM_DIRECT:
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION
