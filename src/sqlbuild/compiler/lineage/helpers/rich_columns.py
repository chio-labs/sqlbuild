"""SQLGlot-backed rich column lineage analyzer."""

from __future__ import annotations

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import Node, lineage

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.helpers.columns import (
    _build_schema_mapping,
    _build_star_lineage,
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
from sqlbuild.shared.helpers.diagnostics_logging import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.lineage")


def build_rich_project_column_lineage(
    project: CompiledProject,
    *,
    dialect: str | None = None,
    model_names: frozenset[str] | None = None,
) -> ProjectColumnLineage | None:
    """Build a rich project column lineage graph using SQLGlot."""

    if not project.settings.sql_analysis:
        return None

    schema: dict[str, dict[str, str]] = _build_schema_mapping(project)
    model_results: dict[str, ModelColumnLineage] = {}
    collapsed_edges: list[ColumnLineageEdge] = []

    for model in project.models:
        if model_names is not None and model.name not in model_names:
            continue
        result: ModelColumnLineage | None = _build_sqlglot_model_column_lineage(
            model,
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


def _build_sqlglot_model_column_lineage(
    model: CompiledModel,
    *,
    schema: dict[str, dict[str, str]],
    dialect: str | None,
) -> ModelColumnLineage | None:
    normalized_sql: str
    physical_resources: tuple[_PhysicalResource, ...]
    normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
    resource_by_physical_name: dict[str, _PhysicalResource] = {
        resource.physical_name: resource for resource in physical_resources
    }
    sqlglot_dialect: str | None = _sqlglot_dialect(dialect)
    try:
        parsed: exp.Expr = sqlglot.parse_one(normalized_sql, dialect=sqlglot_dialect)
    except SqlglotError as error:
        log_debug_event(
            _DEBUG_LOGGER,
            "rich column lineage parse failed; skipping model",
            sqlbuild_model=model.name,
            sqlbuild_error=str(error),
        )
        return None
    select: exp.Select | None = (
        parsed if isinstance(parsed, exp.Select) else parsed.find(exp.Select)
    )
    if select is None:
        return None

    trace_schema: dict[str, dict[str, str]] = _augment_schema_with_referenced_columns(
        parsed=parsed,
        schema=schema,
        physical_names=frozenset(resource_by_physical_name),
    )

    lineages: list[ColumnLineage] = []
    for projection in select.selects:
        if _is_star_projection(projection):
            continue
        output_column: str = projection.alias_or_name
        if not output_column:
            continue
        upstream_columns: tuple[ColumnLineageSource, ...] = _trace_projection_upstreams(
            output_column=output_column,
            normalized_sql=normalized_sql,
            schema=trace_schema,
            dialect=sqlglot_dialect,
            resource_by_physical_name=resource_by_physical_name,
        )
        transform_kind: ColumnTransformKind = _classify_transform(
            projection=projection,
            upstream_columns=upstream_columns,
        )
        lineages.append(
            ColumnLineage(
                output_column=output_column,
                transform_kind=transform_kind,
                expression_sql=None,
                upstream_columns=upstream_columns,
                nullability=InferredNullability.UNKNOWN,
                confidence=(
                    ColumnLineageConfidence.HIGH
                    if upstream_columns or transform_kind == ColumnTransformKind.CONSTANT
                    else ColumnLineageConfidence.UNKNOWN
                ),
            )
        )

    has_star: bool = _select_has_star(select)
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


def _augment_schema_with_referenced_columns(
    *,
    parsed: exp.Expr,
    schema: dict[str, dict[str, str]],
    physical_names: frozenset[str],
) -> dict[str, dict[str, str]]:
    """Register referenced physical relations that lack a known schema.

    SQLGlot returns an unresolvable Placeholder leaf when a column references a
    table that is present in the query but missing from the schema. Seeding such
    relations with the columns referenced against them lets SQLGlot bind them as
    real tables so lineage terminates at the upstream relation.
    """

    referenced_columns: dict[str, set[str]] = {}
    alias_to_physical: dict[str, str] = _table_alias_to_physical_name(
        parsed=parsed,
        physical_names=physical_names,
    )
    sole_physical_name: str | None = _sole_physical_relation(
        parsed=parsed,
        physical_names=physical_names,
    )
    column: exp.Column
    for column in parsed.find_all(exp.Column):
        table_reference: str = column.table
        resolved_physical_name: str | None
        if table_reference:
            resolved_physical_name = alias_to_physical.get(table_reference)
        else:
            resolved_physical_name = sole_physical_name
        if resolved_physical_name is None or resolved_physical_name in schema:
            continue
        referenced_columns.setdefault(resolved_physical_name, set()).add(column.name)
    if not referenced_columns:
        return schema
    augmented: dict[str, dict[str, str]] = dict(schema)
    referenced_physical_name: str
    columns: set[str]
    for referenced_physical_name, columns in referenced_columns.items():
        augmented[referenced_physical_name] = {
            column_name: "UNKNOWN" for column_name in sorted(columns)
        }
    return augmented


def _sole_physical_relation(
    *,
    parsed: exp.Expr,
    physical_names: frozenset[str],
) -> str | None:
    referenced: set[str] = {
        table.name for table in parsed.find_all(exp.Table) if table.name in physical_names
    }
    if len(referenced) == 1:
        return next(iter(referenced))
    return None


def _table_alias_to_physical_name(
    *,
    parsed: exp.Expr,
    physical_names: frozenset[str],
) -> dict[str, str]:
    alias_to_physical: dict[str, str] = {}
    table: exp.Table
    for table in parsed.find_all(exp.Table):
        physical_name: str = table.name
        if physical_name not in physical_names:
            continue
        alias_to_physical[physical_name] = physical_name
        alias_name: str = table.alias
        if alias_name:
            alias_to_physical[alias_name] = physical_name
    return alias_to_physical


def _trace_projection_upstreams(
    *,
    output_column: str,
    normalized_sql: str,
    schema: dict[str, dict[str, str]],
    dialect: str | None,
    resource_by_physical_name: dict[str, _PhysicalResource],
) -> tuple[ColumnLineageSource, ...]:
    try:
        root: Node = lineage(
            output_column,
            normalized_sql,
            schema=schema,
            dialect=dialect,
        )
    except (SqlglotError, KeyError, ValueError) as error:
        log_debug_event(
            _DEBUG_LOGGER,
            "rich column lineage trace failed; skipping column",
            sqlbuild_column=output_column,
            sqlbuild_error=str(error),
        )
        return ()
    sources: list[ColumnLineageSource] = []
    seen: set[tuple[str, str]] = set()
    for leaf in _table_leaf_nodes(root):
        upstream: ColumnLineageSource | None = _leaf_to_source(
            leaf=leaf,
            resource_by_physical_name=resource_by_physical_name,
        )
        if upstream is None:
            continue
        identity: tuple[str, str] = (upstream.resource_name, upstream.column_name)
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(upstream)
    return tuple(sources)


def _table_leaf_nodes(root: Node) -> list[Node]:
    leaves: list[Node] = []
    stack: list[Node] = list(root.downstream)
    visited: set[int] = set()
    while stack:
        node: Node = stack.pop()
        node_id: int = id(node)
        if node_id in visited:
            continue
        visited.add(node_id)
        if node.downstream:
            stack.extend(node.downstream)
            continue
        if isinstance(node.source, exp.Table):
            leaves.append(node)
    return leaves


def _leaf_to_source(
    *,
    leaf: Node,
    resource_by_physical_name: dict[str, _PhysicalResource],
) -> ColumnLineageSource | None:
    source: exp.Expr = leaf.source
    if not isinstance(source, exp.Table):
        return None
    physical_name: str = source.name
    resource: _PhysicalResource | None = resource_by_physical_name.get(physical_name)
    if resource is None:
        return None
    raw_name: str = leaf.name
    column_name: str = raw_name.rsplit(".", 1)[-1] if "." in raw_name else raw_name
    if not column_name:
        return None
    return ColumnLineageSource(
        resource_type=resource.resource_type,
        resource_name=resource.resource_name,
        column_name=column_name,
    )


def _sqlglot_dialect(dialect: str | None) -> str | None:
    if dialect is None:
        return None
    normalized: str = dialect.strip().lower()
    if normalized in ("", "generic", "ansi"):
        return None
    return normalized


def _classify_transform(
    *,
    projection: exp.Expr,
    upstream_columns: tuple[ColumnLineageSource, ...],
) -> ColumnTransformKind:
    inner: exp.Expr = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(inner, exp.Cast):
        return ColumnTransformKind.CAST
    if inner.find(exp.AggFunc) is not None:
        return ColumnTransformKind.AGGREGATION
    if not upstream_columns:
        return ColumnTransformKind.CONSTANT
    if isinstance(inner, exp.Column):
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION


def _is_star_projection(projection: exp.Expr) -> bool:
    if isinstance(projection, exp.Star):
        return True
    return isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)


def _select_has_star(select: exp.Select) -> bool:
    return any(_is_star_projection(projection) for projection in select.selects)
