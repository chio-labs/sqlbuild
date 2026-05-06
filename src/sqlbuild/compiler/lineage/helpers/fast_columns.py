"""Fast SQLGlot-AST column lineage analyzer."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.helpers.columns import (
    _build_schema_mapping,
    _build_star_lineage,
    _expression_sql,
    _normalize_sqlbuild_refs,
    _PhysicalResource,
)
from sqlbuild.compiler.lineage.models import (
    ColumnLineage,
    ColumnLineageEdge,
    ColumnLineageSource,
    ModelColumnLineage,
    ProjectColumnLineage,
    QualifiedLineageColumn,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.shared.helpers.sqlglot import import_sqlglot, import_sqlglot_expressions


def build_fast_project_column_lineage(
    project: CompiledProject,
    *,
    dialect: str | None = None,
) -> ProjectColumnLineage | None:
    """Build a fast, partial project column lineage graph for compiled models."""

    if not project.settings.sqlglot:
        return None

    sqlglot: Any | None = import_sqlglot()
    exp: Any | None = import_sqlglot_expressions()
    if sqlglot is None or exp is None:
        return None

    schema: dict[str, dict[str, str]] = _build_schema_mapping(project)
    model_results: dict[str, ModelColumnLineage] = {}
    collapsed_edges: list[ColumnLineageEdge] = []

    for model in project.models:
        result: ModelColumnLineage | None = _build_fast_model_column_lineage(
            model,
            schema=schema,
            dialect=dialect,
            sqlglot=sqlglot,
            exp=exp,
        )
        if result is None:
            continue
        model_results[model.name] = result
        for column in result.columns:
            target: QualifiedLineageColumn = QualifiedLineageColumn(
                resource_type=CompiledResourceType.MODEL,
                resource_name=model.name,
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


def _build_fast_model_column_lineage(
    model: CompiledModel,
    *,
    schema: dict[str, dict[str, str]],
    dialect: str | None,
    sqlglot: Any,
    exp: Any,
) -> ModelColumnLineage | None:
    normalized_sql: str
    physical_resources: tuple[_PhysicalResource, ...]
    normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
    try:
        parsed: Any = sqlglot.parse_one(normalized_sql, dialect=dialect)
    except Exception:
        return None

    if not isinstance(parsed, exp.Select):
        return None

    alias_map: dict[str, _PhysicalResource] = _table_alias_map(
        parsed,
        physical_resources=physical_resources,
        exp=exp,
    )
    lineages: list[ColumnLineage] = []
    has_star: bool = False
    projections: tuple[Any, ...] = tuple(parsed.expressions)
    inferred_names: tuple[str, ...] = tuple(column.name for column in model.inferred_columns or ())

    for index, projection in enumerate(projections):
        if isinstance(projection, exp.Star):
            has_star = True
            continue
        if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
            has_star = True
            continue
        output_column: str | None = _projection_output_name(
            projection,
            index=index,
            inferred_names=inferred_names,
        )
        if output_column is None:
            continue
        upstream_columns, confidence = _projection_upstream_columns(
            projection,
            alias_map=alias_map,
            exp=exp,
        )
        transform_kind: ColumnTransformKind = _classify_fast_transform(
            projection,
            upstream_columns=upstream_columns,
            exp=exp,
        )
        lineages.append(
            ColumnLineage(
                output_column=output_column,
                transform_kind=transform_kind,
                expression_sql=_expression_sql(projection),
                upstream_columns=upstream_columns,
                nullability=InferredNullability.UNKNOWN,
                confidence=confidence
                if upstream_columns or transform_kind == ColumnTransformKind.CONSTANT
                else ColumnLineageConfidence.UNKNOWN,
            )
        )

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


def _table_alias_map(
    parsed: Any,
    *,
    physical_resources: tuple[_PhysicalResource, ...],
    exp: Any,
) -> dict[str, _PhysicalResource]:
    physical_resource_by_name: dict[str, _PhysicalResource] = {
        resource.physical_name: resource for resource in physical_resources
    }
    alias_map: dict[str, _PhysicalResource] = {}
    table: Any
    for table in parsed.find_all(exp.Table):
        resource: _PhysicalResource | None = physical_resource_by_name.get(table.name)
        if resource is None:
            continue
        alias_map[table.name] = resource
        alias_or_name: str = str(table.alias_or_name or "")
        if alias_or_name:
            alias_map[alias_or_name] = resource
    return alias_map


def _projection_output_name(
    projection: Any, *, index: int, inferred_names: tuple[str, ...]
) -> str | None:
    raw_name: object | None = getattr(projection, "alias_or_name", None)
    if raw_name is not None and str(raw_name):
        return str(raw_name)
    if index < len(inferred_names):
        return inferred_names[index]
    return None


def _projection_upstream_columns(
    projection: Any,
    *,
    alias_map: dict[str, _PhysicalResource],
    exp: Any,
) -> tuple[tuple[ColumnLineageSource, ...], ColumnLineageConfidence]:
    columns: list[ColumnLineageSource] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
    for column in projection.find_all(exp.Column):
        if isinstance(column.this, exp.Star):
            continue
        resource: _PhysicalResource | None = None
        table_name: str = str(column.table or "")
        if table_name:
            resource = alias_map.get(table_name)
        elif len({resource.resource_name for resource in alias_map.values()}) == 1:
            resource = next(iter(alias_map.values()))
            confidence = ColumnLineageConfidence.MEDIUM
        else:
            confidence = ColumnLineageConfidence.UNKNOWN
        if resource is None:
            continue
        column_name: str = str(column.name)
        key: tuple[CompiledResourceType, str, str] = (
            resource.resource_type,
            resource.resource_name,
            column_name,
        )
        if key in seen:
            continue
        seen.add(key)
        columns.append(
            ColumnLineageSource(
                resource_type=resource.resource_type,
                resource_name=resource.resource_name,
                column_name=column_name,
            )
        )
    return tuple(columns), confidence


def _classify_fast_transform(
    projection: Any,
    *,
    upstream_columns: tuple[ColumnLineageSource, ...],
    exp: Any,
) -> ColumnTransformKind:
    inner: Any = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(inner, exp.Star):
        return ColumnTransformKind.STAR
    if isinstance(inner, exp.Cast):
        return ColumnTransformKind.CAST
    if any(isinstance(candidate, exp.AggFunc) for candidate in inner.walk()):
        return ColumnTransformKind.AGGREGATION
    if not upstream_columns:
        return ColumnTransformKind.CONSTANT
    if isinstance(inner, exp.Column) and len(upstream_columns) == 1:
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION
