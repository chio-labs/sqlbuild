"""Fast Polyglot-backed column lineage analyzer."""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage._helpers.columns import (
    _build_schema_mapping,
    _build_star_lineage,
    _normalize_sqlbuild_refs,
)
from sqlbuild.compiler.lineage.constants import STAR_COLUMN_NAME
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
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_AGGREGATE_KINDS,
    POLYGLOT_CAST_KINDS,
    POLYGLOT_KIND_ALIAS,
    POLYGLOT_KIND_COLUMN,
    POLYGLOT_KIND_SELECT,
    POLYGLOT_KIND_TABLE,
    POLYGLOT_KIND_UNION,
    POLYGLOT_SET_OPERATION_KINDS,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.lineage")


def build_fast_project_column_lineage(
    *,
    project: CompiledProject,
    dialect: str | None = None,
    model_names: frozenset[str] | None = None,
) -> ProjectColumnLineage | None:
    """Build a fast, partial project column lineage graph for compiled models."""

    if not project.settings.sql_analysis:
        return None

    schema: dict[str, dict[str, str]] = _build_schema_mapping(project)
    model_results: dict[str, ModelColumnLineage] = {}
    collapsed_edges: list[ColumnLineageEdge] = []

    for model in project.models:
        if model_names is not None and model.name not in model_names:
            continue
        result: ModelColumnLineage | None = _build_polyglot_fast_model_column_lineage(
            model=model,
            schema=schema,
            dialect=dialect,
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


def _build_polyglot_fast_model_column_lineage(
    *,
    model: CompiledModel,
    schema: dict[str, dict[str, str]],
    dialect: str | None,
) -> ModelColumnLineage | None:
    if model.fast_lineage_columns is not None:
        lineages: list[ColumnLineage] = []
        for fact in model.fast_lineage_columns:
            upstream_columns: list[ColumnLineageSource] = []
            for source in fact.upstream_columns:
                upstream_columns.append(
                    ColumnLineageSource(
                        resource_type=source.resource_type,
                        resource_name=source.resource_name,
                        column_name=source.column_name,
                    )
                )
            lineages.append(
                ColumnLineage(
                    output_column=fact.output_column,
                    transform_kind=fact.transform_kind,
                    expression_sql=None,
                    upstream_columns=tuple(upstream_columns),
                    nullability=InferredNullability.UNKNOWN,
                    confidence=fact.confidence,
                )
            )
        if model.fast_lineage_has_star:
            normalized_sql: str
            physical_resources: tuple[PhysicalResource, ...]
            normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
            del normalized_sql
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
            has_star=model.fast_lineage_has_star,
        )

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None
    normalized_sql: str
    physical_resources: tuple[PhysicalResource, ...]
    normalized_sql, physical_resources = _normalize_sqlbuild_refs(model.query_sql)
    try:
        parsed: Any = polyglot_module.parse_one(normalized_sql, dialect=dialect or "generic")
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="fast column lineage parse failed; falling back",
            sqlbuild_model=model.name,
            sqlbuild_error=str(error),
        )
        return None
    parsed_kind: str = str(getattr(parsed, "kind", ""))
    if parsed_kind == POLYGLOT_KIND_UNION:
        return _build_polyglot_union_model_column_lineage(
            model=model,
            parsed=parsed,
            schema=schema,
            physical_resources=physical_resources,
        )
    if parsed_kind != POLYGLOT_KIND_SELECT:
        return None

    alias_map: dict[str, PhysicalResource] = _polyglot_table_alias_map(
        parsed=parsed,
        physical_resources=physical_resources,
    )
    unqualified_resource: PhysicalResource | None = _single_alias_resource(alias_map)
    lineages: list[ColumnLineage] = []
    has_star: bool = False
    projections: tuple[Any, ...] = tuple(getattr(parsed, "expressions", ()))
    inferred_names: tuple[str, ...] = tuple(column.name for column in model.inferred_columns or ())
    for index, projection in enumerate(projections):
        if bool(getattr(projection, "is_star", False)):
            has_star = True
            continue
        inner: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == POLYGLOT_KIND_ALIAS
            else projection
        )
        if bool(getattr(inner, "is_star", False)):
            has_star = True
            continue
        output_column: str | None = _polyglot_projection_output_name(
            projection=projection,
            index=index,
            inferred_names=inferred_names,
        )
        if output_column is None:
            continue
        upstream_columns, confidence = _polyglot_projection_upstream_columns(
            projection=projection,
            alias_map=alias_map,
            unqualified_resource=unqualified_resource,
        )
        transform_kind: ColumnTransformKind = _polyglot_classify_transform(
            expression=inner,
            upstream_columns=upstream_columns,
        )
        lineages.append(
            ColumnLineage(
                output_column=output_column,
                transform_kind=transform_kind,
                expression_sql=None,
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
    return ModelColumnLineage(model_name=model.name, columns=tuple(lineages), has_star=has_star)


def _build_polyglot_union_model_column_lineage(
    *,
    model: CompiledModel,
    parsed: Any,
    schema: dict[str, dict[str, str]],
    physical_resources: tuple[PhysicalResource, ...],
) -> ModelColumnLineage | None:
    selects: tuple[Any, ...] = _polyglot_set_expression_selects(parsed)
    if not selects:
        return None
    inferred_names: tuple[str, ...] = tuple(column.name for column in model.inferred_columns or ())
    max_projection_count: int = max(
        (len(tuple(getattr(select, "expressions", ()) or ())) for select in selects),
        default=0,
    )
    lineages: list[ColumnLineage] = []
    has_star: bool = False
    for index in range(max_projection_count):
        output_column: str | None = inferred_names[index] if index < len(inferred_names) else None
        upstream_columns: list[ColumnLineageSource] = []
        seen: set[tuple[CompiledResourceType, str, str]] = set()
        confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
        transform_kind: ColumnTransformKind = ColumnTransformKind.DIRECT
        for select in selects:
            projections: tuple[Any, ...] = tuple(getattr(select, "expressions", ()) or ())
            if index >= len(projections):
                continue
            projection: Any = projections[index]
            if bool(getattr(projection, "is_star", False)):
                has_star = True
                continue
            inner: Any = (
                projection.this
                if str(getattr(projection, "kind", "")) == POLYGLOT_KIND_ALIAS
                else projection
            )
            if bool(getattr(inner, "is_star", False)):
                has_star = True
                continue
            if output_column is None:
                output_column = _polyglot_projection_output_name(
                    projection=projection,
                    index=index,
                    inferred_names=inferred_names,
                )
            alias_map: dict[str, PhysicalResource] = _polyglot_table_alias_map(
                parsed=select,
                physical_resources=physical_resources,
            )
            branch_upstream, branch_confidence = _polyglot_projection_upstream_columns(
                projection=projection,
                alias_map=alias_map,
                unqualified_resource=_single_alias_resource(alias_map),
            )
            if branch_confidence == ColumnLineageConfidence.UNKNOWN:
                confidence = ColumnLineageConfidence.UNKNOWN
            elif (
                branch_confidence == ColumnLineageConfidence.MEDIUM
                and confidence == ColumnLineageConfidence.HIGH
            ):
                confidence = ColumnLineageConfidence.MEDIUM
            branch_transform: ColumnTransformKind = _polyglot_classify_transform(
                expression=inner,
                upstream_columns=branch_upstream,
            )
            if branch_transform != ColumnTransformKind.DIRECT:
                transform_kind = branch_transform
            for source in branch_upstream:
                key: tuple[CompiledResourceType, str, str] = (
                    CompiledResourceType(source.resource_type),
                    source.resource_name,
                    source.column_name,
                )
                if key in seen:
                    continue
                seen.add(key)
                upstream_columns.append(source)
        if output_column is None:
            continue
        if not upstream_columns and transform_kind != ColumnTransformKind.CONSTANT:
            confidence = ColumnLineageConfidence.UNKNOWN
        lineages.append(
            ColumnLineage(
                output_column=output_column,
                transform_kind=transform_kind,
                expression_sql=None,
                upstream_columns=tuple(upstream_columns),
                nullability=InferredNullability.UNKNOWN,
                confidence=confidence,
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
    return ModelColumnLineage(model_name=model.name, columns=tuple(lineages), has_star=has_star)


def _polyglot_set_expression_selects(expression: Any) -> tuple[Any, ...]:
    kind: str = str(getattr(expression, "kind", ""))
    if kind == POLYGLOT_KIND_SELECT:
        return (expression,)
    if kind not in POLYGLOT_SET_OPERATION_KINDS:
        return ()
    args: object = getattr(expression, "args", {})
    if not isinstance(args, dict):
        return ()
    selects: list[Any] = []
    for child_name in ("left", "right"):
        child: object = args.get(child_name)
        if child is not None:
            selects.extend(_polyglot_set_expression_selects(child))
    return tuple(selects)


def _polyglot_table_alias_map(
    *,
    parsed: Any,
    physical_resources: tuple[PhysicalResource, ...],
) -> dict[str, PhysicalResource]:
    physical_resource_by_name: dict[str, PhysicalResource] = {
        resource.physical_name: resource for resource in physical_resources
    }
    physical_resource_by_name.update(
        {resource.resource_name: resource for resource in physical_resources}
    )
    alias_map: dict[str, PhysicalResource] = {}
    try:
        tables: tuple[Any, ...] = tuple(parsed.find_all(POLYGLOT_KIND_TABLE))
    except Exception:
        return alias_map
    for table in tables:
        table_name: str = str(getattr(table, "name", "") or "")
        resource: PhysicalResource | None = physical_resource_by_name.get(table_name)
        if resource is None:
            continue
        alias_map[table_name] = resource
        alias_or_name: str = str(getattr(table, "alias_or_name", "") or "")
        if alias_or_name:
            alias_map[alias_or_name] = resource
    return alias_map


def _polyglot_projection_output_name(
    *, projection: Any, index: int, inferred_names: tuple[str, ...]
) -> str | None:
    raw_name: str = str(getattr(projection, "output_name", "") or "")
    if raw_name and raw_name != STAR_COLUMN_NAME:
        return raw_name
    raw_name = str(getattr(projection, "alias_or_name", "") or "")
    if raw_name and raw_name != STAR_COLUMN_NAME:
        return raw_name
    if index < len(inferred_names):
        return inferred_names[index]
    return None


def _polyglot_projection_upstream_columns(
    *,
    projection: Any,
    alias_map: dict[str, PhysicalResource],
    unqualified_resource: PhysicalResource | None,
) -> tuple[tuple[ColumnLineageSource, ...], ColumnLineageConfidence]:
    columns: list[ColumnLineageSource] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
    column_refs: tuple[tuple[str, str], ...] = _polyglot_column_refs_in_expression(projection)
    for column_name, table_name in column_refs:
        if not column_name:
            continue
        resource: PhysicalResource | None = None
        if table_name:
            resource = alias_map.get(table_name)
        elif unqualified_resource is not None:
            resource = unqualified_resource
            confidence = ColumnLineageConfidence.MEDIUM
        else:
            confidence = ColumnLineageConfidence.UNKNOWN
        if resource is None:
            continue
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


def _single_alias_resource(alias_map: dict[str, PhysicalResource]) -> PhysicalResource | None:
    resource: PhysicalResource | None = None
    for candidate in alias_map.values():
        if resource is None:
            resource = candidate
            continue
        if candidate.resource_name != resource.resource_name:
            return None
    return resource


def _polyglot_column_refs_in_expression(expression: Any) -> tuple[tuple[str, str], ...]:
    if str(getattr(expression, "kind", "")) == POLYGLOT_KIND_COLUMN:
        return (
            (str(getattr(expression, "name", "") or ""), _polyglot_column_table_name(expression)),
        )
    try:
        payload: object = expression.to_dict()
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="fast column lineage expression payload extraction failed; falling back",
            sqlbuild_error=str(error),
        )
        return ()
    refs: list[tuple[str, str]] = []

    def visit(node: object, collected_refs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        if isinstance(node, dict):
            node_dict: dict[str, object] = cast(dict[str, object], node)
            column_payload: object = node_dict.get("column")
            if isinstance(column_payload, dict):
                column_dict: dict[str, object] = cast(dict[str, object], column_payload)
                column_name: str = _polyglot_name_payload_value(column_dict.get("name"))
                table_payload: object = column_dict.get("table")
                table_name: str = ""
                if isinstance(table_payload, dict):
                    table_dict: dict[str, object] = cast(dict[str, object], table_payload)
                    table_name = _polyglot_name_payload_value(table_dict.get("name"))
                return [*collected_refs, (column_name, table_name)]
            for value in node_dict.values():
                collected_refs = visit(value, collected_refs)
        elif isinstance(node, list):
            for value in node:
                collected_refs = visit(value, collected_refs)
        return collected_refs

    refs = visit(payload, refs)
    return tuple(refs)


def _polyglot_name_payload_value(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        payload_dict: dict[str, object] = cast(dict[str, object], payload)
        name: object = payload_dict.get("name")
        if isinstance(name, str):
            return name
    return ""


def _polyglot_column_table_name(column: Any) -> str:
    try:
        payload: object = column.to_dict().get("column", {})
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="fast column lineage column table extraction failed; falling back",
            sqlbuild_error=str(error),
        )
        return ""
    if not isinstance(payload, dict):
        return ""
    table_payload: object = payload.get("table")
    if not isinstance(table_payload, dict):
        return ""
    raw_name: object = table_payload.get("name")
    return raw_name if isinstance(raw_name, str) else ""


def _polyglot_columns_in_expression(expression: Any) -> tuple[Any, ...]:
    if str(getattr(expression, "kind", "")) == POLYGLOT_KIND_COLUMN:
        return (expression,)
    columns: list[Any] = []
    seen: set[int] = set()

    def visit(node: Any, visited: set[int], found: list[Any]) -> tuple[set[int], list[Any]]:
        node_id: int = id(node)
        if node_id in visited:
            return visited, found
        visited = visited | {node_id}
        if str(getattr(node, "kind", "")) == POLYGLOT_KIND_COLUMN:
            return visited, [*found, node]
        for child in _polyglot_child_expressions(node):
            visited, found = visit(child, visited, found)
        return visited, found

    seen, columns = visit(expression, seen, columns)
    return tuple(columns)


def _polyglot_child_expressions(expression: Any) -> tuple[Any, ...]:
    children: list[Any] = []
    for attr_name in ("this", "expression", "left", "right"):
        child: Any | None = getattr(expression, attr_name, None)
        if child is not None and str(getattr(child, "kind", "")):
            children.append(child)
    for child in getattr(expression, "expressions", ()) or ():
        if str(getattr(child, "kind", "")):
            children.append(child)
    return tuple(children)


def _polyglot_classify_transform(
    *,
    expression: Any,
    upstream_columns: tuple[ColumnLineageSource, ...],
) -> ColumnTransformKind:
    kind: str = str(getattr(expression, "kind", ""))
    if bool(getattr(expression, "is_star", False)):
        return ColumnTransformKind.STAR
    if kind in POLYGLOT_CAST_KINDS:
        return ColumnTransformKind.CAST
    if _polyglot_has_aggregation(expression):
        return ColumnTransformKind.AGGREGATION
    if not upstream_columns:
        return ColumnTransformKind.CONSTANT
    if kind == POLYGLOT_KIND_COLUMN and len(upstream_columns) == 1:
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION


def _polyglot_has_aggregation(expression: Any) -> bool:
    try:
        nodes: tuple[Any, ...] = tuple(expression.walk())
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="fast column lineage aggregation detection failed; falling back",
            sqlbuild_error=str(error),
        )
        return False
    return any(str(getattr(node, "kind", "")) in POLYGLOT_AGGREGATE_KINDS for node in nodes)
