"""Required SQL analysis-backed output inference, binding, and lineage facts."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any, cast

from sqlbuild.adapter.contract.constants import POLYGLOT_CUSTOM_TYPE_NAME
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.compile._helpers.analysis.cte_facts import (
    _polyglot_cte_passthrough_nullability_from_parsed,
    _polyglot_cte_passthrough_types_from_parsed,
    _polyglot_expression_is_non_null_after_filter,
    _polyglot_non_null_filter_context,
    _polyglot_top_level_ctes,
    _unwrap_polyglot_annotations,
)
from sqlbuild.compiler.compile.constants import (
    DECIMAL_SQL_TYPE_NAME,
    SQL_QUALIFIER_SEPARATOR_TOKEN,
    SQL_WILDCARD_TOKEN,
)
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
    NonNullFilterContext,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_AGGREGATE_KINDS as _POLYGLOT_AGGREGATE_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_BOOLEAN_RESULT_KINDS as _POLYGLOT_BOOLEAN_RESULT_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_CAST_KINDS as _POLYGLOT_CAST_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_JOIN_FULL as _POLYGLOT_JOIN_FULL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_JOIN_LEFT as _POLYGLOT_JOIN_LEFT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_JOIN_RIGHT as _POLYGLOT_JOIN_RIGHT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_ALIAS as _POLYGLOT_KIND_ALIAS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_CAST as _POLYGLOT_KIND_CAST,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_COALESCE as _POLYGLOT_KIND_COALESCE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_COLUMN as _POLYGLOT_KIND_COLUMN,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_COUNT as _POLYGLOT_KIND_COUNT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_IS_NULL as _POLYGLOT_KIND_IS_NULL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_LITERAL as _POLYGLOT_KIND_LITERAL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_NULL as _POLYGLOT_KIND_NULL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_SELECT as _POLYGLOT_KIND_SELECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_TABLE as _POLYGLOT_KIND_TABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_TIMESTAMP as _POLYGLOT_KIND_TIMESTAMP,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_KIND_TRY_CAST as _POLYGLOT_KIND_TRY_CAST,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_ALIAS as _POLYGLOT_PAYLOAD_ALIAS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_COLUMN as _POLYGLOT_PAYLOAD_COLUMN,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_DATA_TYPE as _POLYGLOT_PAYLOAD_DATA_TYPE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_EXPRESSIONS as _POLYGLOT_PAYLOAD_EXPRESSIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_FROM as _POLYGLOT_PAYLOAD_FROM,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_JOINS as _POLYGLOT_PAYLOAD_JOINS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_KIND as _POLYGLOT_PAYLOAD_KIND,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_NAME as _POLYGLOT_PAYLOAD_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_PRECISION as _POLYGLOT_PAYLOAD_PRECISION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_SCALE as _POLYGLOT_PAYLOAD_SCALE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_SELECT as _POLYGLOT_PAYLOAD_SELECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_TABLE as _POLYGLOT_PAYLOAD_TABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_THIS as _POLYGLOT_PAYLOAD_THIS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_TIMEZONE as _POLYGLOT_PAYLOAD_TIMEZONE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_PAYLOAD_TO as _POLYGLOT_PAYLOAD_TO,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_SET_OPERATION_KINDS as _POLYGLOT_SET_OPERATION_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_VARCHAR_DATA_TYPES as _POLYGLOT_VARCHAR_DATA_TYPES,
)
from sqlbuild.compiler.sql_analysis.constants import (
    TIMESTAMP_WITH_TIME_ZONE_SQL_TYPE_NAME as _TIMESTAMP_WITH_TIME_ZONE_SQL_TYPE_NAME,
)
from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")
_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"@@@(\w+)")
_QUALIFIED_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(
    r'(?<![A-Za-z0-9_$])(?:"(?P<double>[^"]+)"|`(?P<backtick>[^`]+)`|'
    r"\[(?P<bracket>[^\]]+)\]|(?P<plain>[A-Za-z_$][A-Za-z0-9_$]*))"
    r"(?:\s|--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)*\.",
    re.DOTALL,
)


def _infer_columns_with_polyglot(
    *,
    cleaned_sql: str,
    dialect: str | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> tuple[InferredColumn, ...] | None | bool:
    polyglot_module: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot_module.parse_one(cleaned_sql, dialect=dialect or "generic")
    except polyglot_module.PolyglotError as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column inference parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return False
    return _infer_columns_from_polyglot_ast(
        parsed=parsed,
        column_nullability_by_table=column_nullability_by_table,
        inference_profile=inference_profile,
    )


def _infer_columns_from_polyglot_ast(
    *,
    parsed: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> tuple[InferredColumn, ...] | None | bool:
    infer_nullability: bool = str(getattr(parsed, "kind", "")) not in _POLYGLOT_SET_OPERATION_KINDS
    select: Any | None = parsed
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        select = parsed.find(_POLYGLOT_KIND_SELECT)
    if select is None or str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return None

    column_nullability_by_table = dict(column_nullability_by_table)
    alias_nullability: dict[str, InferredNullability] = {}
    if _has_known_nullability(column_nullability_by_table):
        alias_nullability = _polyglot_alias_nullability_from_select(
            select=select,
            column_nullability_by_table=column_nullability_by_table,
        )
    top_level_ctes: tuple[tuple[str, Any, bool], ...] = _polyglot_top_level_ctes(parsed)
    referenced_table_names: tuple[str, ...] = (
        tuple(
            str(getattr(table, "name", "") or "") for table in parsed.find_all(_POLYGLOT_KIND_TABLE)
        )
        if top_level_ctes
        else ()
    )
    cte_passthrough_types: dict[str, str] = _polyglot_cte_passthrough_types_from_parsed(
        parsed=parsed,
        column_types_by_table={},
        inference_profile=inference_profile,
        expression_type_resolver=_polyglot_expression_type,
        top_level_ctes=top_level_ctes,
        referenced_table_names=referenced_table_names,
    )
    cte_passthrough_nullability: dict[str, InferredNullability] = (
        _polyglot_cte_passthrough_nullability_from_parsed(
            parsed=parsed,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
            nullability_resolver=_infer_polyglot_nullability,
            shallow_nullability_resolver=_infer_polyglot_shallow_nullability,
            alias_nullability_resolver=_polyglot_alias_nullability_from_select,
            top_level_ctes=top_level_ctes,
            referenced_table_names=referenced_table_names,
        )
    )
    non_null_filter_context: NonNullFilterContext | None = _polyglot_non_null_filter_context(
        select=select,
        column_nullability_by_table=column_nullability_by_table,
    )
    columns: list[InferredColumn] = []
    projection: Any
    for projection in getattr(select, "expressions", ()):
        projection = _unwrap_polyglot_annotations(projection)
        if bool(getattr(projection, "is_star", False)):
            continue
        name: str = str(getattr(projection, "output_name", "") or "")
        if not name or name == SQL_WILDCARD_TOKEN:
            continue
        inner: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
            else projection
        )
        col_type: str | None = cte_passthrough_types.get(name) or _polyglot_expression_type(
            expression=inner,
            inference_profile=inference_profile,
        )
        nullability: InferredNullability = InferredNullability.UNKNOWN
        if infer_nullability:
            nullability = (
                InferredNullability.NON_NULL
                if _polyglot_expression_is_non_null_after_filter(
                    expression=inner,
                    context=non_null_filter_context,
                )
                else cte_passthrough_nullability.get(
                    name,
                    _infer_polyglot_nullability(
                        expression=inner,
                        alias_nullability=alias_nullability,
                        column_nullability_by_table=column_nullability_by_table,
                        inference_profile=inference_profile,
                    ),
                )
            )
        columns.append(InferredColumn(name=name, type=col_type, nullability=nullability))
    return tuple(columns)


def _analyze_columns_and_lineage_from_polyglot_ast(
    *,
    parsed: Any,
    references: tuple[CompileSqlReference, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    recover_cte_facts: bool,
) -> tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool]:
    infer_nullability: bool = str(getattr(parsed, "kind", "")) not in _POLYGLOT_SET_OPERATION_KINDS
    select: Any | None = parsed
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        select = parsed.find(_POLYGLOT_KIND_SELECT)
    if select is None or str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return None, (), False

    column_nullability_by_table = dict(column_nullability_by_table)
    has_known_nullability: bool = _has_known_nullability(column_nullability_by_table)
    alias_nullability: dict[str, InferredNullability] = {}
    if has_known_nullability:
        alias_nullability = _polyglot_alias_nullability_from_select(
            select=select,
            column_nullability_by_table=column_nullability_by_table,
        )
    alias_map: dict[str, tuple[CompiledResourceType, str]] = _polyglot_reference_alias_map(
        parsed=select,
        references=references,
    )
    unqualified_resource: tuple[CompiledResourceType, str] | None = _single_alias_resource(
        alias_map
    )

    top_level_ctes: tuple[tuple[str, Any, bool], ...] = (
        _polyglot_top_level_ctes(parsed) if recover_cte_facts else ()
    )
    referenced_table_names: tuple[str, ...] = (
        tuple(
            str(getattr(table, "name", "") or "") for table in parsed.find_all(_POLYGLOT_KIND_TABLE)
        )
        if top_level_ctes
        else ()
    )
    cte_passthrough_types: dict[str, str] = (
        _polyglot_cte_passthrough_types_from_parsed(
            parsed=parsed,
            column_types_by_table=column_types_by_table,
            inference_profile=inference_profile,
            expression_type_resolver=_polyglot_expression_type,
            top_level_ctes=top_level_ctes,
            referenced_table_names=referenced_table_names,
        )
        if recover_cte_facts
        else {}
    )
    cte_passthrough_nullability: dict[str, InferredNullability] = (
        _polyglot_cte_passthrough_nullability_from_parsed(
            parsed=parsed,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
            nullability_resolver=_infer_polyglot_nullability,
            shallow_nullability_resolver=_infer_polyglot_shallow_nullability,
            alias_nullability_resolver=_polyglot_alias_nullability_from_select,
            top_level_ctes=top_level_ctes,
            referenced_table_names=referenced_table_names,
        )
        if recover_cte_facts
        else {}
    )
    non_null_filter_context: NonNullFilterContext | None = _polyglot_non_null_filter_context(
        select=select,
        column_nullability_by_table=column_nullability_by_table,
    )
    columns: list[InferredColumn] = []
    lineage_columns: list[CompiledLineageColumnFact] = []
    has_star: bool = False
    projection: Any
    for projection in getattr(select, "expressions", ()):
        projection = _unwrap_polyglot_annotations(projection)
        if bool(getattr(projection, "is_star", False)):
            has_star = True
            continue
        inner: Any = (
            projection.this
            if str(getattr(projection, "kind", "")) == _POLYGLOT_KIND_ALIAS
            else projection
        )
        if bool(getattr(inner, "is_star", False)):
            has_star = True
            continue
        output_column: str = str(getattr(projection, "output_name", "") or "")
        if not output_column or output_column == SQL_WILDCARD_TOKEN:
            continue
        col_type: str | None = cte_passthrough_types.get(
            output_column
        ) or _polyglot_expression_type(
            expression=inner,
            inference_profile=inference_profile,
        )
        nullability: InferredNullability = InferredNullability.UNKNOWN
        if infer_nullability:
            nullability = (
                InferredNullability.NON_NULL
                if _polyglot_expression_is_non_null_after_filter(
                    expression=inner,
                    context=non_null_filter_context,
                )
                else (
                    cte_passthrough_nullability[output_column]
                    if output_column in cte_passthrough_nullability
                    else (
                        _infer_polyglot_nullability(
                            expression=inner,
                            alias_nullability=alias_nullability,
                            column_nullability_by_table=column_nullability_by_table,
                            inference_profile=inference_profile,
                        )
                        if has_known_nullability
                        else _infer_polyglot_shallow_nullability(
                            expression=inner,
                            inference_profile=inference_profile,
                        )
                    )
                )
            )
        columns.append(InferredColumn(name=output_column, type=col_type, nullability=nullability))

        upstream_columns, confidence = _polyglot_lineage_upstream_columns(
            projection=projection,
            alias_map=alias_map,
            unqualified_resource=unqualified_resource,
        )
        transform_kind: ColumnTransformKind = _polyglot_lineage_transform_kind(
            expression=inner,
            has_upstream=bool(upstream_columns),
        )
        lineage_columns.append(
            CompiledLineageColumnFact(
                output_column=output_column,
                upstream_columns=upstream_columns,
                transform_kind=transform_kind,
                confidence=confidence
                if upstream_columns or transform_kind == ColumnTransformKind.CONSTANT
                else ColumnLineageConfidence.UNKNOWN,
            )
        )
    return tuple(columns), tuple(lineage_columns), has_star


def _polyglot_reference_alias_map(
    *, parsed: Any, references: tuple[CompileSqlReference, ...]
) -> dict[str, tuple[CompiledResourceType, str]]:
    resource_by_name: dict[str, tuple[CompiledResourceType, str]] = {}
    reference: CompileSqlReference
    for reference in references:
        resource_type: CompiledResourceType | None = _lineage_resource_type(reference)
        if resource_type is None:
            continue
        resource_by_name[_analysis_reference_name(reference)] = (
            resource_type,
            reference.ref_name,
        )
    alias_map: dict[str, tuple[CompiledResourceType, str]] = {}
    tables: tuple[Any, ...] = tuple(parsed.find_all(_POLYGLOT_KIND_TABLE))
    table: Any
    for table in tables:
        table_name: str = str(getattr(table, "name", "") or "")
        resource: tuple[CompiledResourceType, str] | None = resource_by_name.get(table_name)
        if resource is None:
            continue
        alias_map[table_name] = resource
        alias_or_name: str = str(getattr(table, "alias_or_name", "") or "")
        if alias_or_name:
            alias_map[alias_or_name] = resource
    return alias_map


def _lineage_resource_type(reference: CompileSqlReference) -> CompiledResourceType | None:
    if reference.ref_kind == SqlReferenceKind.REF:
        return CompiledResourceType.MODEL
    if reference.ref_kind == SqlReferenceKind.SOURCE:
        return CompiledResourceType.SOURCE
    if reference.ref_kind == SqlReferenceKind.SEED:
        return CompiledResourceType.SEED
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return CompiledResourceType.TABLE_FN
    return None


def _analysis_reference_name(reference: CompileSqlReference) -> str:
    if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
        return table_function_analysis_name(reference.ref_name)
    return reference.ref_name


def table_function_analysis_name(function_name: str) -> str:
    """Return the stable relation stub used to analyze a table-function call."""

    return f"__sqlbuild_table_function_{function_name}"


def _polyglot_lineage_upstream_columns(
    *,
    projection: Any,
    alias_map: dict[str, tuple[CompiledResourceType, str]],
    unqualified_resource: tuple[CompiledResourceType, str] | None,
) -> tuple[tuple[CompiledLineageSourceFact, ...], ColumnLineageConfidence]:
    columns: list[CompiledLineageSourceFact] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
    column_refs: tuple[tuple[str, str], ...] = _polyglot_column_refs_in_expression(projection)
    for column_name, table_name in column_refs:
        if not column_name:
            continue
        resource: tuple[CompiledResourceType, str] | None = None
        if table_name:
            resource = alias_map.get(table_name)
        elif unqualified_resource is not None:
            resource = unqualified_resource
            confidence = ColumnLineageConfidence.MEDIUM
        else:
            confidence = ColumnLineageConfidence.UNKNOWN
        if resource is None:
            continue
        resource_type, resource_name = resource
        key: tuple[CompiledResourceType, str, str] = (resource_type, resource_name, column_name)
        if key in seen:
            continue
        seen.add(key)
        columns.append(
            CompiledLineageSourceFact(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=column_name,
            )
        )
    return tuple(columns), confidence


def _single_alias_resource(
    alias_map: dict[str, tuple[CompiledResourceType, str]],
) -> tuple[CompiledResourceType, str] | None:
    resource: tuple[CompiledResourceType, str] | None = None
    for candidate in alias_map.values():
        if resource is None:
            resource = candidate
            continue
        if candidate[1] != resource[1]:
            return None
    return resource


def _polyglot_column_refs_in_expression(expression: Any) -> tuple[tuple[str, str], ...]:
    if str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_COLUMN:
        return (
            (str(getattr(expression, "name", "") or ""), _polyglot_column_table_name(expression)),
        )
    payload: object = expression.to_dict()
    refs: list[tuple[str, str]] = []

    def visit(*, node: object, collected_refs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        if isinstance(node, dict):
            node_dict: dict[str, object] = cast(dict[str, object], node)
            column_payload: object = node_dict.get(_POLYGLOT_PAYLOAD_COLUMN)
            if isinstance(column_payload, dict):
                column_dict: dict[str, object] = cast(dict[str, object], column_payload)
                column_name: str = _polyglot_name_payload_value(
                    column_dict.get(_POLYGLOT_PAYLOAD_NAME)
                )
                table_payload: object = column_dict.get(_POLYGLOT_PAYLOAD_TABLE)
                table_name: str = ""
                if isinstance(table_payload, dict):
                    table_dict: dict[str, object] = cast(dict[str, object], table_payload)
                    table_name = _polyglot_name_payload_value(
                        table_dict.get(_POLYGLOT_PAYLOAD_NAME)
                    )
                return [*collected_refs, (column_name, table_name)]
            for value in node_dict.values():
                collected_refs = visit(node=value, collected_refs=collected_refs)
        elif isinstance(node, list):
            for value in node:
                collected_refs = visit(node=value, collected_refs=collected_refs)
        return collected_refs

    refs = visit(node=payload, collected_refs=refs)
    return tuple(refs)


def _has_known_nullability(
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> bool:
    for column_facts in column_nullability_by_table.values():
        for value in column_facts.values():
            if value != InferredNullability.UNKNOWN:
                return True
    return False


def _polyglot_lineage_transform_kind(*, expression: Any, has_upstream: bool) -> ColumnTransformKind:
    kind: str = str(getattr(expression, "kind", ""))
    if bool(getattr(expression, "is_star", False)):
        return ColumnTransformKind.STAR
    if kind in _POLYGLOT_CAST_KINDS:
        return ColumnTransformKind.CAST
    if _polyglot_has_aggregation(expression):
        return ColumnTransformKind.AGGREGATION
    if not has_upstream:
        return ColumnTransformKind.CONSTANT
    if kind == _POLYGLOT_KIND_COLUMN:
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION


def _polyglot_has_aggregation(expression: Any) -> bool:
    nodes: tuple[Any, ...] = tuple(expression.walk())
    return any(str(getattr(node, "kind", "")) in _POLYGLOT_AGGREGATE_KINDS for node in nodes)


def _polyglot_expression_type(
    *, expression: Any, inference_profile: ExpressionInferenceProfile
) -> str | None:
    kind: str = str(getattr(expression, "kind", ""))
    function_name: str = str(getattr(expression, "name", "")) or kind
    function_type: str | None = (
        inference_profile.function_return_type(function_name)
        if kind != _POLYGLOT_KIND_COLUMN
        else None
    )
    if function_type is not None:
        return function_type
    if kind in _POLYGLOT_BOOLEAN_RESULT_KINDS:
        return "BOOLEAN"
    if kind not in _POLYGLOT_CAST_KINDS:
        return None
    payload: object = expression.to_dict().get(kind, {})
    if not isinstance(payload, dict):
        return None
    target: object = payload.get(_POLYGLOT_PAYLOAD_TO)
    if not isinstance(target, dict):
        return None
    raw_type: object = target.get(_POLYGLOT_PAYLOAD_DATA_TYPE)
    if not isinstance(raw_type, str) or not raw_type:
        return None
    if raw_type.upper() == POLYGLOT_CUSTOM_TYPE_NAME:
        custom_name: object = target.get(_POLYGLOT_PAYLOAD_NAME)
        if isinstance(custom_name, str) and custom_name:
            return custom_name.upper()
    if (
        raw_type.lower() == _POLYGLOT_KIND_TIMESTAMP
        and target.get(_POLYGLOT_PAYLOAD_TIMEZONE) is True
    ):
        return _TIMESTAMP_WITH_TIME_ZONE_SQL_TYPE_NAME
    type_name: str = _polyglot_type_name(raw_type)
    length: object = target.get("length")
    if raw_type.lower() in _POLYGLOT_VARCHAR_DATA_TYPES and isinstance(length, int):
        return f"VARCHAR({length})"
    precision: object = target.get(_POLYGLOT_PAYLOAD_PRECISION)
    scale: object = target.get(_POLYGLOT_PAYLOAD_SCALE)
    if type_name == DECIMAL_SQL_TYPE_NAME and isinstance(precision, int):
        if isinstance(scale, int):
            return f"DECIMAL({precision}, {scale})"
        return f"DECIMAL({precision})"
    return type_name


def _polyglot_type_name(raw_type: str) -> str:
    known_types: dict[str, str] = {
        "big_int": "BIGINT",
        "bool": "BOOLEAN",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "decimal": "DECIMAL",
        "double": "DOUBLE",
        "float": "FLOAT",
        "int": "INT",
        "integer": "INT",
        "text": "TEXT",
        "timestamp": "TIMESTAMP",
        "var_char": "TEXT",
        "varchar": "TEXT",
    }
    return known_types.get(raw_type, raw_type.replace("_", " ").upper())


def _infer_polyglot_nullability(
    *,
    expression: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> InferredNullability:
    kind: str = str(getattr(expression, "kind", ""))
    if kind == _POLYGLOT_KIND_NULL:
        return InferredNullability.NULLABLE
    if kind == _POLYGLOT_KIND_LITERAL:
        return InferredNullability.NON_NULL
    if kind == _POLYGLOT_KIND_COLUMN:
        return _infer_polyglot_column_nullability(
            expression=expression,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
        )
    if kind == _POLYGLOT_KIND_CAST:
        inner: Any | None = getattr(expression, "this", None)
        if inner is None:
            return InferredNullability.UNKNOWN
        return _infer_polyglot_nullability(
            expression=inner,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
    if kind == _POLYGLOT_KIND_TRY_CAST:
        return InferredNullability.UNKNOWN
    if kind == _POLYGLOT_KIND_COUNT:
        return InferredNullability.NON_NULL
    if kind == _POLYGLOT_KIND_IS_NULL:
        return InferredNullability.NON_NULL
    if kind == _POLYGLOT_KIND_COALESCE:
        child_nullabilities: list[InferredNullability] = [
            _infer_polyglot_nullability(
                expression=child,
                alias_nullability=alias_nullability,
                column_nullability_by_table=column_nullability_by_table,
                inference_profile=inference_profile,
            )
            for child in _polyglot_expression_args(expression)
        ]
        if any(value == InferredNullability.NON_NULL for value in child_nullabilities):
            return InferredNullability.NON_NULL
        if child_nullabilities and all(
            value == InferredNullability.NULLABLE for value in child_nullabilities
        ):
            return InferredNullability.NULLABLE
        return InferredNullability.UNKNOWN
    rule: FunctionNullabilityRule | None = inference_profile.function_nullability_rule(kind)
    if rule is None:
        return InferredNullability.UNKNOWN
    child_nullabilities: tuple[InferredNullability, ...] = tuple(
        _infer_polyglot_nullability(
            expression=child,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
        for child in _polyglot_expression_args(expression)
    )
    return rule(child_nullabilities)


def _infer_polyglot_shallow_nullability(
    *,
    expression: Any,
    inference_profile: ExpressionInferenceProfile,
) -> InferredNullability:
    kind: str = str(getattr(expression, "kind", ""))
    if kind == _POLYGLOT_KIND_NULL:
        return InferredNullability.NULLABLE
    if kind == _POLYGLOT_KIND_LITERAL:
        return InferredNullability.NON_NULL
    if kind == _POLYGLOT_KIND_COUNT:
        return InferredNullability.NON_NULL
    if kind == _POLYGLOT_KIND_IS_NULL:
        return InferredNullability.NON_NULL
    if kind == _POLYGLOT_KIND_COLUMN:
        return InferredNullability.UNKNOWN
    if kind == _POLYGLOT_KIND_CAST:
        inner: Any | None = getattr(expression, "this", None)
        if inner is None:
            return InferredNullability.UNKNOWN
        return _infer_polyglot_shallow_nullability(
            expression=inner,
            inference_profile=inference_profile,
        )
    if kind == _POLYGLOT_KIND_TRY_CAST:
        return InferredNullability.UNKNOWN
    if kind == _POLYGLOT_KIND_COALESCE:
        child_nullabilities: tuple[InferredNullability, ...] = tuple(
            _infer_polyglot_shallow_nullability(
                expression=child,
                inference_profile=inference_profile,
            )
            for child in _polyglot_expression_args(expression)
        )
        if any(value == InferredNullability.NON_NULL for value in child_nullabilities):
            return InferredNullability.NON_NULL
        if child_nullabilities and all(
            value == InferredNullability.NULLABLE for value in child_nullabilities
        ):
            return InferredNullability.NULLABLE
        return InferredNullability.UNKNOWN
    rule: FunctionNullabilityRule | None = inference_profile.function_nullability_rule(kind)
    if rule is None:
        return InferredNullability.UNKNOWN
    child_nullabilities: tuple[InferredNullability, ...] = tuple(
        _infer_polyglot_shallow_nullability(
            expression=child,
            inference_profile=inference_profile,
        )
        for child in _polyglot_expression_args(expression)
    )
    return rule(child_nullabilities)


def _infer_polyglot_column_nullability(
    *,
    expression: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> InferredNullability:
    column_name: str = str(getattr(expression, "name", "") or "")
    if not column_name:
        return InferredNullability.UNKNOWN
    payload: object = expression.to_dict().get(_POLYGLOT_PAYLOAD_COLUMN, {})
    table_name: str = ""
    if isinstance(payload, dict):
        table_payload: object = payload.get(_POLYGLOT_PAYLOAD_TABLE)
        if isinstance(table_payload, dict):
            raw_name: object = table_payload.get(_POLYGLOT_PAYLOAD_NAME)
            if isinstance(raw_name, str):
                table_name = raw_name
    if table_name:
        table_fact: InferredNullability = alias_nullability.get(
            table_name, InferredNullability.UNKNOWN
        )
        if table_fact == InferredNullability.NULLABLE:
            return InferredNullability.NULLABLE
        return column_nullability_by_table.get(table_name, {}).get(
            column_name, InferredNullability.UNKNOWN
        )
    matches: list[InferredNullability] = [
        columns[column_name]
        for columns in column_nullability_by_table.values()
        if column_name in columns
    ]
    if len(matches) == 1:
        return matches[0]
    return InferredNullability.UNKNOWN


def _polyglot_column_table_name(column: Any) -> str:
    payload: object = column.to_dict().get(_POLYGLOT_PAYLOAD_COLUMN, {})
    if not isinstance(payload, dict):
        return ""
    table_payload: object = payload.get(_POLYGLOT_PAYLOAD_TABLE)
    if not isinstance(table_payload, dict):
        return ""
    raw_name: object = table_payload.get(_POLYGLOT_PAYLOAD_NAME)
    return raw_name if isinstance(raw_name, str) else ""


def _polyglot_expression_args(expression: Any) -> tuple[Any, ...]:
    args: list[Any] = []
    primary_arg: Any | None = getattr(expression, "this", None)
    if primary_arg is not None:
        args.append(primary_arg)
    args.extend(getattr(expression, "expressions", ()) or ())
    return tuple(args)


def _polyglot_alias_nullability_from_select(
    *,
    select: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> dict[str, InferredNullability]:
    alias_nullability: dict[str, InferredNullability] = {}
    current_aliases: set[str] = set()

    select_payload: object = select.to_dict().get(_POLYGLOT_PAYLOAD_SELECT, {})
    if not isinstance(select_payload, dict):
        return alias_nullability

    from_payload: object = select_payload.get(_POLYGLOT_PAYLOAD_FROM)
    if isinstance(from_payload, dict):
        from_expressions: object = from_payload.get(_POLYGLOT_PAYLOAD_EXPRESSIONS)
        if isinstance(from_expressions, list) and len(from_expressions) == 1:
            from_table_payload: object = from_expressions[0]
            if isinstance(from_table_payload, dict):
                table_payload: object = from_table_payload.get(_POLYGLOT_PAYLOAD_TABLE)
                if isinstance(table_payload, dict):
                    alias, table_name = _polyglot_table_payload_alias_and_name(table_payload)
                    current_aliases.add(alias)
                    alias_nullability[alias] = InferredNullability.UNKNOWN
                    _copy_table_facts_to_alias(
                        alias=alias,
                        table_name=table_name,
                        column_nullability_by_table=column_nullability_by_table,
                    )

    joins_payload: object = select_payload.get(_POLYGLOT_PAYLOAD_JOINS)
    if not isinstance(joins_payload, list):
        return alias_nullability
    for join_payload in joins_payload:
        if not isinstance(join_payload, dict):
            continue
        this_payload: object = join_payload.get(_POLYGLOT_PAYLOAD_THIS)
        if not isinstance(this_payload, dict):
            continue
        joined_table_payload: object = this_payload.get(_POLYGLOT_PAYLOAD_TABLE)
        if not isinstance(joined_table_payload, dict):
            continue
        joined_alias, joined_table_name = _polyglot_table_payload_alias_and_name(
            joined_table_payload
        )
        side: str = str(join_payload.get(_POLYGLOT_PAYLOAD_KIND) or "").upper()
        if side == _POLYGLOT_JOIN_LEFT:
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        elif side == _POLYGLOT_JOIN_RIGHT:
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        elif side == _POLYGLOT_JOIN_FULL:
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        else:
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        current_aliases.add(joined_alias)
        _copy_table_facts_to_alias(
            alias=joined_alias,
            table_name=joined_table_name,
            column_nullability_by_table=column_nullability_by_table,
        )
    return alias_nullability


def _polyglot_table_payload_alias_and_name(table_payload: dict[str, object]) -> tuple[str, str]:
    table_name: str = _polyglot_name_payload_value(table_payload.get(_POLYGLOT_PAYLOAD_NAME))
    alias: str = (
        _polyglot_name_payload_value(table_payload.get(_POLYGLOT_PAYLOAD_ALIAS)) or table_name
    )
    return alias, table_name


def _polyglot_name_payload_value(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        payload_dict: dict[str, object] = cast(dict[str, object], payload)
        name: object = payload_dict.get(_POLYGLOT_PAYLOAD_NAME)
        if isinstance(name, str):
            return name
    return ""


def substitute_placeholder_defaults(*, query_sql: str, placeholders: dict[str, str]) -> str:
    """Replace @@@name tokens with their default values for SQL analysis parsing."""

    if not placeholders:
        return query_sql

    def _replacer(match: re.Match[str]) -> str:
        name: str = match.group(1)
        return placeholders.get(name, match.group(0))

    return _PLACEHOLDER_PATTERN.sub(_replacer, query_sql)


def _replace_refs_with_stubs(
    *,
    query_sql: str,
    dialect: str | None = None,
    relation_stubs: dict[str, str] | None = None,
) -> str:
    """Replace SQLBuild marker calls with parseable SQL stubs."""

    return normalize_analysis_sql(sql=query_sql, dialect=dialect, stubs=relation_stubs)


def _qualified_reference_names(*, query_sql: str, reference_names: Iterable[str]) -> frozenset[str]:
    if SQL_QUALIFIER_SEPARATOR_TOKEN not in query_sql:
        return frozenset()
    names_by_normalized: dict[str, list[str]] = {}
    for value in reference_names:
        name: str = str(value)
        names_by_normalized.setdefault(name.casefold(), []).append(name)
    if not names_by_normalized:
        return frozenset()

    qualified: set[str] = set()
    for match in _QUALIFIED_IDENTIFIER_PATTERN.finditer(query_sql):
        identifier: str = next(value for value in match.groups() if value is not None)
        qualified.update(names_by_normalized.get(identifier.casefold(), ()))
    return frozenset(qualified)


def _infer_expression_nullability(
    *,
    expression: Any,
    expressions_module: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> InferredNullability:
    """Infer only nullability facts SQLBuild can prove statically."""

    literal_type: type[Any] = expressions_module.Literal
    null_type: type[Any] = expressions_module.Null
    column_type: type[Any] = expressions_module.Column
    cast_type: type[Any] = expressions_module.Cast
    try_cast_type: type[Any] = expressions_module.TryCast
    coalesce_type: type[Any] = expressions_module.Coalesce
    count_type: type[Any] = expressions_module.Count

    if isinstance(expression, null_type):
        return InferredNullability.NULLABLE
    if isinstance(expression, literal_type):
        return InferredNullability.NON_NULL
    if isinstance(expression, column_type):
        return _infer_column_nullability(
            column=expression,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
        )
    if isinstance(expression, cast_type):
        return _infer_expression_nullability(
            expression=expression.this,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
    if isinstance(expression, try_cast_type):
        return InferredNullability.UNKNOWN
    if isinstance(expression, count_type):
        return InferredNullability.NON_NULL
    if isinstance(expression, coalesce_type):
        return _infer_coalesce_nullability(
            expression=expression,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
    function_name: str = _expression_function_name(expression)
    rule: FunctionNullabilityRule | None = inference_profile.function_nullability_rule(
        function_name
    )
    if rule is None:
        return InferredNullability.UNKNOWN
    arg_nullabilities: tuple[InferredNullability, ...] = tuple(
        _infer_expression_nullability(
            expression=arg,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
        for arg in _expression_function_args(expression)
    )
    return rule(arg_nullabilities)


def _infer_column_nullability(
    *,
    column: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> InferredNullability:
    table_name: str = str(column.table or "")
    column_name: str = str(column.name or "")
    if table_name:
        table_fact: InferredNullability = alias_nullability.get(
            table_name, InferredNullability.UNKNOWN
        )
        if table_fact == InferredNullability.NULLABLE:
            return InferredNullability.NULLABLE
        return column_nullability_by_table.get(table_name, {}).get(
            column_name, InferredNullability.UNKNOWN
        )

    matches: list[InferredNullability] = [
        column_facts[column_name]
        for column_facts in column_nullability_by_table.values()
        if column_name in column_facts
    ]
    if len(matches) == 1:
        return matches[0]
    return InferredNullability.UNKNOWN


def _infer_coalesce_nullability(
    *,
    expression: Any,
    expressions_module: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> InferredNullability:
    arg_nullabilities: tuple[InferredNullability, ...] = tuple(
        _infer_expression_nullability(
            expression=arg,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
        for arg in expression.expressions
    )
    if any(value == InferredNullability.NON_NULL for value in arg_nullabilities):
        return InferredNullability.NON_NULL
    if arg_nullabilities and all(
        value == InferredNullability.NULLABLE for value in arg_nullabilities
    ):
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN


def _expression_function_name(expression: Any) -> str:
    sql_name: object | None = getattr(expression, "sql_name", None)
    if callable(sql_name):
        return str(sql_name()).upper()
    key: object | None = getattr(expression, "key", None)
    return str(key or "").upper()


def _expression_function_args(expression: Any) -> tuple[Any, ...]:
    args: list[Any] = []
    primary_arg: Any | None = getattr(expression, "this", None)
    if primary_arg is not None:
        args.append(primary_arg)
    args.extend(expression.expressions)
    return tuple(args)


def _copy_table_facts_to_alias(
    *,
    alias: str,
    table_name: str,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> None:
    if alias == table_name:
        return
    table_facts: dict[str, InferredNullability] | None = column_nullability_by_table.get(table_name)
    if table_facts is not None:
        alias_facts: dict[str, dict[str, InferredNullability]] = column_nullability_by_table
        alias_facts.setdefault(alias, table_facts)
