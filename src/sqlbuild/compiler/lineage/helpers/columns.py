"""SQLGlot-backed column lineage analyzer."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.helpers.sqlglot import (
    import_sqlglot_lineage,
    import_sqlglot_optimizer,
)
from sqlbuild.compiler.lineage.models import (
    ColumnLineage,
    ColumnLineageEdge,
    ColumnLineageNode,
    ColumnLineageSource,
    InternalColumnLineageEdge,
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

_SQLBUILD_REF_PATTERN: re.Pattern[str] = re.compile(
    r"__(?P<kind>ref|source|seed)\(\s*(['\"])(?P<name>[^'\"]+)\2\s*\)"
)
_SQLBUILD_UDF_PATTERN: re.Pattern[str] = re.compile(
    r"__udf\(\s*(['\"])(?P<name>[^'\"]+)\1\s*\)\s*\("
)


@dataclass(frozen=True)
class _PhysicalResource:
    resource_type: CompiledResourceType
    resource_name: str
    physical_name: str


def build_project_column_lineage(
    project: CompiledProject,
    *,
    dialect: str | None = None,
    model_names: frozenset[str] | None = None,
) -> ProjectColumnLineage | None:
    """Build a sidecar project column lineage graph for compiled models."""

    if not project.settings.sqlglot:
        return None

    sqlglot: Any | None = import_sqlglot()
    exp: Any | None = import_sqlglot_expressions()
    lineage_module: Any | None = import_sqlglot_lineage()
    optimizer: dict[str, Any] | None = import_sqlglot_optimizer()
    if sqlglot is None or exp is None or lineage_module is None or optimizer is None:
        return None

    schema: dict[str, dict[str, str]] = _build_schema_mapping(project)
    model_results: dict[str, ModelColumnLineage] = {}
    collapsed_edges: list[ColumnLineageEdge] = []

    for model in project.models:
        if model_names is not None and model.name not in model_names:
            continue
        result: ModelColumnLineage | None = _build_model_column_lineage(
            model,
            schema=schema,
            dialect=dialect,
            sqlglot=sqlglot,
            exp=exp,
            sqlglot_lineage=lineage_module.lineage,
            qualify=optimizer["qualify"],
            build_scope=optimizer["build_scope"],
        )
        if result is None:
            continue
        model_results[model.name] = result
        target_resource: QualifiedLineageColumn = QualifiedLineageColumn(
            resource_type=CompiledResourceType.MODEL,
            resource_name=model.name,
            column_name="",
        )
        for column in result.columns:
            target: QualifiedLineageColumn = QualifiedLineageColumn(
                resource_type=target_resource.resource_type,
                resource_name=target_resource.resource_name,
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


def _build_model_column_lineage(
    model: CompiledModel,
    *,
    schema: dict[str, dict[str, str]],
    dialect: str | None,
    sqlglot: Any,
    exp: Any,
    sqlglot_lineage: Any,
    qualify: Any,
    build_scope: Any,
) -> ModelColumnLineage | None:
    normalized_sql: str
    physical_resources: tuple[_PhysicalResource, ...]
    normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
    physical_resource_by_name: dict[str, _PhysicalResource] = {
        resource.physical_name: resource for resource in physical_resources
    }
    try:
        parsed: Any = sqlglot.parse_one(normalized_sql, dialect=dialect)
        has_star: bool = _has_star(parsed, exp)
        qualified: Any = qualify(
            parsed,
            dialect=dialect,
            schema=schema,
            validate_qualify_columns=False,
            infer_schema=True,
        )
        scope: Any = build_scope(qualified)
    except Exception:
        return None

    output_columns: tuple[str, ...] = () if has_star else _output_column_names(model, qualified)
    if not output_columns:
        star_lineages: tuple[ColumnLineage, ...] = _build_star_lineage(
            model=model,
            schema=schema,
            physical_resources=physical_resources,
            existing_columns=set(),
        )
        return ModelColumnLineage(
            model_name=model.name,
            columns=star_lineages,
            has_star=has_star,
        )
    lineages: list[ColumnLineage] = []
    for output_column in output_columns:
        try:
            node: Any = sqlglot_lineage(
                output_column,
                sql=qualified,
                scope=scope,
                trim_selects=False,
                dialect=dialect,
                copy=False,
            )
        except Exception:
            continue
        upstream_columns: tuple[ColumnLineageSource, ...] = _extract_upstream_columns(
            node,
            physical_resource_by_name=physical_resource_by_name,
            exp=exp,
        )
        transform_kind: ColumnTransformKind = _classify_transform(
            node.expression,
            upstream_columns,
            output_column=output_column,
            exp=exp,
        )
        nodes, edges = _extract_internal_graph(
            node,
            physical_resource_by_name=physical_resource_by_name,
            exp=exp,
        )
        lineages.append(
            ColumnLineage(
                output_column=output_column,
                transform_kind=transform_kind,
                expression_sql=_expression_sql(node.expression),
                upstream_columns=upstream_columns,
                nullability=InferredNullability.UNKNOWN,
                nodes=nodes,
                edges=edges,
                confidence=ColumnLineageConfidence.HIGH
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


def _normalize_sqlbuild_refs(sql: str) -> tuple[str, tuple[_PhysicalResource, ...]]:
    resources: list[_PhysicalResource] = []

    def replace(match: re.Match[str]) -> str:
        kind: str = match.group("kind")
        name: str = match.group("name")
        resource_type: CompiledResourceType = {
            "ref": CompiledResourceType.MODEL,
            "source": CompiledResourceType.SOURCE,
            "seed": CompiledResourceType.SEED,
        }[kind]
        physical_name: str = _physical_resource_name(resource_type, name)
        resources.append(
            _PhysicalResource(
                resource_type=resource_type,
                resource_name=name,
                physical_name=physical_name,
            )
        )
        return physical_name

    normalized_sql: str = _SQLBUILD_REF_PATTERN.sub(replace, sql)
    normalized_sql = _SQLBUILD_UDF_PATTERN.sub(
        lambda match: f"{_physical_function_name(match.group('name'))}(",
        normalized_sql,
    )
    return normalized_sql, tuple(resources)


def _physical_resource_name(resource_type: CompiledResourceType, resource_name: str) -> str:
    safe_name: str = re.sub(r"[^a-zA-Z0-9_]", "__", resource_name)
    return f"__sqlbuild_{resource_type.value}__{safe_name}"


def _physical_function_name(function_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "__", function_name)


def _build_schema_mapping(project: CompiledProject) -> dict[str, dict[str, str]]:
    schema: dict[str, dict[str, str]] = {}
    for model in project.models:
        columns: dict[str, str] = {}
        for column in model.inferred_columns or ():
            columns[column.name] = column.type or "UNKNOWN"
        for column in model.schema_entry.columns if model.schema_entry is not None else ():
            columns.setdefault(column.name, column.type or "UNKNOWN")
        if columns:
            schema[_physical_resource_name(CompiledResourceType.MODEL, model.name)] = columns
    for source in project.sources:
        columns: dict[str, str] = {
            column.name: column.type or "UNKNOWN" for column in source.source_entry.columns
        }
        if columns:
            schema[_physical_resource_name(CompiledResourceType.SOURCE, source.name)] = columns
    for seed in project.seeds:
        columns: dict[str, str] = {
            column.name: column.type or "UNKNOWN" for column in seed.schema_entry.columns
        }
        if columns:
            schema[_physical_resource_name(CompiledResourceType.SEED, seed.name)] = columns
    return schema


def _output_column_names(model: CompiledModel, qualified: Any) -> tuple[str, ...]:
    if model.inferred_columns is not None:
        return tuple(column.name for column in model.inferred_columns)
    return tuple(getattr(qualified, "named_selects", ()) or ())


def _has_star(expression: Any, exp: Any) -> bool:
    return any(True for _ in expression.find_all(exp.Star))


def _build_star_lineage(
    *,
    model: CompiledModel,
    schema: dict[str, dict[str, str]],
    physical_resources: tuple[_PhysicalResource, ...],
    existing_columns: set[str],
) -> tuple[ColumnLineage, ...]:
    lineages: list[ColumnLineage] = []
    for resource in physical_resources:
        for column_name in schema.get(resource.physical_name, {}):
            if column_name in existing_columns:
                continue
            existing_columns.add(column_name)
            lineages.append(
                ColumnLineage(
                    output_column=column_name,
                    transform_kind=ColumnTransformKind.STAR,
                    expression_sql=None,
                    upstream_columns=(
                        ColumnLineageSource(
                            resource_type=resource.resource_type,
                            resource_name=resource.resource_name,
                            column_name=column_name,
                        ),
                    ),
                    nullability=InferredNullability.UNKNOWN,
                    confidence=ColumnLineageConfidence.MEDIUM,
                )
            )
    return tuple(lineages)


def _extract_upstream_columns(
    node: Any,
    *,
    physical_resource_by_name: dict[str, _PhysicalResource],
    exp: Any,
) -> tuple[ColumnLineageSource, ...]:
    columns: list[ColumnLineageSource] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    for leaf in _leaf_nodes(node):
        table: str | None = _table_name_from_leaf(leaf, exp=exp)
        column: str | None = _column_name_from_leaf(leaf)
        if table is None or column is None:
            continue
        resource: _PhysicalResource | None = physical_resource_by_name.get(table)
        if resource is None:
            continue
        key: tuple[CompiledResourceType, str, str] = (
            resource.resource_type,
            resource.resource_name,
            column,
        )
        if key in seen:
            continue
        seen.add(key)
        columns.append(
            ColumnLineageSource(
                resource_type=resource.resource_type,
                resource_name=resource.resource_name,
                column_name=column,
            )
        )
    return tuple(columns)


def _leaf_nodes(node: Any) -> Iterable[Any]:
    return (candidate for candidate in node.walk() if not candidate.downstream)


def _table_name_from_leaf(leaf: Any, *, exp: Any) -> str | None:
    expression: Any = leaf.expression
    if not isinstance(expression, exp.Table):
        return None
    return expression.this.name


def _column_name_from_leaf(leaf: Any) -> str | None:
    name: str = str(leaf.name).strip('"')
    if "." in name:
        return name.rsplit(".", 1)[-1].strip('"')
    return name or None


def _extract_internal_graph(
    node: Any,
    *,
    physical_resource_by_name: dict[str, _PhysicalResource],
    exp: Any,
) -> tuple[tuple[ColumnLineageNode, ...], tuple[InternalColumnLineageEdge, ...]]:
    nodes: list[ColumnLineageNode] = []
    edges: list[InternalColumnLineageEdge] = []
    node_ids: dict[int, str] = {}
    for index, current in enumerate(node.walk()):
        node_id: str = f"n{index}"
        node_ids[id(current)] = node_id
        table: str | None = _table_name_from_leaf(current, exp=exp)
        resource: _PhysicalResource | None = (
            physical_resource_by_name.get(table) if table is not None else None
        )
        nodes.append(
            ColumnLineageNode(
                id=node_id,
                name=str(current.name),
                expression_sql=_expression_sql(current.expression),
                source_sql=_expression_sql(current.source),
                resource_type=resource.resource_type if resource is not None else None,
                resource_name=resource.resource_name if resource is not None else None,
                scope_name=current.reference_node_name or None,
            )
        )
    for current in node.walk():
        downstream_id: str | None = node_ids.get(id(current))
        if downstream_id is None:
            continue
        for child in current.downstream:
            upstream_id: str | None = node_ids.get(id(child))
            if upstream_id is not None:
                edges.append(
                    InternalColumnLineageEdge(
                        upstream_node_id=upstream_id,
                        downstream_node_id=downstream_id,
                    )
                )
    return tuple(nodes), tuple(edges)


def _expression_sql(expression: Any) -> str | None:
    sql: Any = getattr(expression, "sql", None)
    if sql is None:
        return None
    try:
        return sql()
    except Exception:
        return None


def _classify_transform(
    expression: Any,
    upstream_columns: tuple[ColumnLineageSource, ...],
    *,
    output_column: str,
    exp: Any,
) -> ColumnTransformKind:
    inner: Any = expression.this if isinstance(expression, exp.Alias) else expression
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
    if upstream_columns and all(source.column_name == output_column for source in upstream_columns):
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION
