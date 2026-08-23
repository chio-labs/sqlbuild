"""Optional SQL analysis-backed output column inference from model query SQL."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.compile.constants import (
    DECIMAL_SQL_TYPE_NAME,
    FULL_JOIN_SIDE,
    LEFT_JOIN_SIDE,
    RESOLVED_SOURCE_CONFIDENCE,
    RIGHT_JOIN_SIDE,
    SQL_WILDCARD_TOKEN,
    UNKNOWN_SQL_TYPE_NAME,
)
from sqlbuild.compiler.compile.models import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.references.main._quoted_reference_call_pattern import (
    quoted_reference_call_pattern,
)
from sqlbuild.compiler.references.main.reference_call_prefix_pattern_text import (
    reference_call_prefix_pattern_text,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_AGGREGATE_KINDS as _POLYGLOT_AGGREGATE_KINDS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_BASE_TABLES as _POLYGLOT_ANALYSIS_BASE_TABLES,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_CAST_TYPE as _POLYGLOT_ANALYSIS_CAST_TYPE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_IS_STAR as _POLYGLOT_ANALYSIS_IS_STAR,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NAME as _POLYGLOT_ANALYSIS_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NULLABILITY as _POLYGLOT_ANALYSIS_NULLABILITY,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL as _POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE as _POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_PROJECTIONS as _POLYGLOT_ANALYSIS_PROJECTIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_RELATIONS as _POLYGLOT_ANALYSIS_RELATIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE as _POLYGLOT_ANALYSIS_SHAPE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE_SELECT as _POLYGLOT_ANALYSIS_SHAPE_SELECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION as _POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SOURCE_ALIAS as _POLYGLOT_ANALYSIS_SOURCE_ALIAS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE as _POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_SOURCE_NAME as _POLYGLOT_ANALYSIS_SOURCE_NAME,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_STAR_PROJECTIONS as _POLYGLOT_ANALYSIS_STAR_PROJECTIONS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TABLE as _POLYGLOT_ANALYSIS_TABLE,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION as _POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_CAST as _POLYGLOT_ANALYSIS_TRANSFORM_CAST,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT as _POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_DIRECT as _POLYGLOT_ANALYSIS_TRANSFORM_DIRECT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_KIND as _POLYGLOT_ANALYSIS_TRANSFORM_KIND,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TRANSFORM_STAR as _POLYGLOT_ANALYSIS_TRANSFORM_STAR,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_TYPE_HINT as _POLYGLOT_ANALYSIS_TYPE_HINT,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_UNSAFE_TRANSFORMS as _POLYGLOT_ANALYSIS_UNSAFE_TRANSFORMS,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_ANALYSIS_UPSTREAM as _POLYGLOT_ANALYSIS_UPSTREAM,
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
    POLYGLOT_PAYLOAD_TO as _POLYGLOT_PAYLOAD_TO,
)
from sqlbuild.compiler.sql_analysis.constants import (
    POLYGLOT_SET_OPERATION_KINDS as _POLYGLOT_SET_OPERATION_KINDS,
)
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.compile")
_REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.REF)
_SEED_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SEED)
_SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)
_DBT_REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.DBT_REF)
_UDF_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.UDF)}"
    r'"([A-Za-z_][A-Za-z0-9_]*)"\)\s*(?=\()'
)
_TABLE_FUNCTION_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.TABLE_FUNCTION)}"
    r'"([A-Za-z_][A-Za-z0-9_]*)"\)\s*(?=\()'
)
_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"@@@(\w+)")


@lru_cache(maxsize=1)
def _warn_once_polyglot_module_missing() -> None:
    """Warn once per process when the Polyglot module cannot be imported."""

    _DEBUG_LOGGER.warning(
        "Polyglot SQL module is not importable; SQL validation, column inference, "
        "and column lineage are disabled for this run"
    )


def infer_columns_with_sql_analysis(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> tuple[InferredColumn, ...] | None:
    """Infer output columns from model query SQL using SQL analysis."""

    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql, placeholders=placeholders
        )

    polyglot_columns: tuple[InferredColumn, ...] | None | bool = _infer_columns_with_polyglot(
        cleaned_sql=cleaned_sql,
        dialect=profile.sql_analysis_dialect,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )
    if isinstance(polyglot_columns, tuple):
        return polyglot_columns
    return None


def analyze_columns_with_polyglot(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> tuple[InferredColumn, ...] | None | bool:
    """Infer columns with one Polyglot parse, returning False when unavailable."""

    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql, placeholders=placeholders
        )
    return _infer_columns_with_polyglot(
        cleaned_sql=cleaned_sql,
        dialect=profile.sql_analysis_dialect,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )


def analyze_columns_and_lineage_with_polyglot(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...] = (),
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    column_types_by_table: dict[str, dict[str, str]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
    allow_compact_analysis: bool = False,
) -> PolyglotAnalysisResult:
    """Infer columns and compact lineage facts from one Polyglot parse."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        _warn_once_polyglot_module_missing()
        return PolyglotAnalysisResult(analysis_succeeded=False)
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(
            query_sql=cleaned_sql, placeholders=placeholders
        )
    compact_analysis: (
        tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool] | None
    ) = _analyze_columns_and_lineage_with_compact_polyglot(
        polyglot_module=polyglot_module,
        cleaned_sql=cleaned_sql,
        dialect=profile.sql_analysis_dialect,
        references=references,
        column_nullability_by_table=column_nullability_by_table or {},
        column_types_by_table=column_types_by_table or {},
        inference_profile=profile,
        allow_compact_analysis=allow_compact_analysis,
    )
    if compact_analysis is not None:
        return PolyglotAnalysisResult(
            analysis_succeeded=True,
            columns=compact_analysis[0],
            lineage_columns=compact_analysis[1],
            has_star=compact_analysis[2],
        )
    try:
        parsed: Any = polyglot_module.parse_one(
            cleaned_sql,
            dialect=profile.sql_analysis_dialect or "generic",
        )
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column and lineage analysis parse failed; falling back",
            sqlbuild_error=str(error),
        )
        return PolyglotAnalysisResult(analysis_succeeded=False)
    columns, lineage_columns, has_star = _analyze_columns_and_lineage_from_polyglot_ast(
        parsed=parsed,
        references=references,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )
    return PolyglotAnalysisResult(
        analysis_succeeded=True,
        columns=columns,
        lineage_columns=lineage_columns,
        has_star=has_star,
    )


def _analyze_columns_and_lineage_with_compact_polyglot(
    *,
    polyglot_module: Any,
    cleaned_sql: str,
    dialect: str | None,
    references: tuple[CompileSqlReference, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
) -> tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool] | None:
    if not allow_compact_analysis:
        return None
    try:
        options: dict[str, object] = {"dialect": dialect or "generic"}
        schema: dict[str, object] | None = _compact_analysis_schema(
            column_nullability_by_table=column_nullability_by_table,
            column_types_by_table=column_types_by_table,
            table_names=frozenset(_analysis_reference_name(reference) for reference in references),
        )
        if schema is not None:
            options["schema"] = schema
        analysis: Any = polyglot_module.analyze_query(cleaned_sql, options)
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="compact query analysis failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    if not isinstance(analysis, dict):
        return None
    projections: object = analysis.get(_POLYGLOT_ANALYSIS_PROJECTIONS)
    if not isinstance(projections, list):
        return None
    if not _compact_analysis_is_eligible(analysis=analysis, projections=projections):
        return None
    reference_map: dict[str, tuple[CompiledResourceType, str]] = _lineage_reference_map(references)
    relation_alias_by_name: dict[str, str | None] = _compact_relation_alias_by_name(analysis)
    columns: list[InferredColumn] = []
    lineage_columns: list[CompiledLineageColumnFact] = []
    has_star: bool = _compact_analysis_has_star(analysis)
    infer_nullability: bool = (
        analysis.get(_POLYGLOT_ANALYSIS_SHAPE) != _POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION
    )
    for projection in projections:
        if not isinstance(projection, dict):
            return None
        if bool(projection.get(_POLYGLOT_ANALYSIS_IS_STAR)):
            continue
        output_column: str = str(projection.get(_POLYGLOT_ANALYSIS_NAME) or "")
        if not output_column or output_column == SQL_WILDCARD_TOKEN:
            continue
        columns.append(
            InferredColumn(
                name=output_column,
                type=_compact_projection_type(projection),
                nullability=_compact_projection_nullability(
                    projection=projection,
                    infer_nullability=infer_nullability,
                ),
            )
        )
        upstream_columns, confidence = _compact_lineage_upstream_columns(
            projection=projection,
            reference_map=reference_map,
            relation_alias_by_name=relation_alias_by_name,
        )
        transform_kind: ColumnTransformKind = _compact_transform_kind(
            projection=projection,
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
    if has_star and len(references) == 1:
        schema_name: str = _analysis_reference_name(references[0])
        declared_order: dict[str, int] = {
            column_name: index
            for index, column_name in enumerate(
                column_nullability_by_table.get(schema_name, {})
            )
        }
        fallback_order: int = len(declared_order)
        columns.sort(key=lambda column: declared_order.get(column.name, fallback_order))
        lineage_columns.sort(
            key=lambda column: declared_order.get(column.output_column, fallback_order)
        )
    return tuple(columns), tuple(lineage_columns), has_star


def _compact_analysis_is_eligible(*, analysis: dict[str, Any], projections: list[object]) -> bool:
    shape: object = analysis.get(_POLYGLOT_ANALYSIS_SHAPE)
    if shape not in {_POLYGLOT_ANALYSIS_SHAPE_SELECT, _POLYGLOT_ANALYSIS_SHAPE_SET_OPERATION}:
        return False
    projection: object
    for projection in projections:
        if not isinstance(projection, dict):
            return False
        projection_dict: dict[str, Any] = cast(dict[str, Any], projection)
        transform_kind: str = str(projection_dict.get(_POLYGLOT_ANALYSIS_TRANSFORM_KIND) or "")
        if transform_kind in _POLYGLOT_ANALYSIS_UNSAFE_TRANSFORMS:
            return False
        upstream_values: object = projection_dict.get(_POLYGLOT_ANALYSIS_UPSTREAM)
        if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_CAST and (
            not isinstance(upstream_values, list) or not upstream_values
        ):
            return False
    return True


def _compact_analysis_schema(
    *,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    table_names: frozenset[str] | None = None,
) -> dict[str, object] | None:
    tables: list[dict[str, object]] = []
    table_name: str
    columns: dict[str, InferredNullability]
    for table_name, columns in sorted(column_nullability_by_table.items()):
        if table_names is not None and table_name not in table_names:
            continue
        if not columns:
            continue
        tables.append(
            {
                "name": table_name,
                "columns": [
                    _compact_analysis_schema_column(
                        column_name=column_name,
                        column_type=column_types_by_table.get(table_name, {}).get(
                            column_name, "UNKNOWN"
                        ),
                        nullability=columns[column_name],
                    )
                    for column_name in columns
                ],
            }
        )
    if not tables:
        return None
    return {"tables": tables}


def _compact_analysis_schema_column(
    *,
    column_name: str,
    column_type: str,
    nullability: InferredNullability,
) -> dict[str, object]:
    column: dict[str, object] = {"name": column_name, "type": column_type}
    if nullability == InferredNullability.NON_NULL:
        column["nullable"] = False
    elif nullability == InferredNullability.NULLABLE:
        column["nullable"] = True
    return column


def _lineage_reference_map(
    references: tuple[CompileSqlReference, ...],
) -> dict[str, tuple[CompiledResourceType, str]]:
    reference_map: dict[str, tuple[CompiledResourceType, str]] = {}
    reference: CompileSqlReference
    for reference in references:
        resource_type: CompiledResourceType | None = _lineage_resource_type(reference)
        if resource_type is None:
            continue
        reference_map[_analysis_reference_name(reference)] = (
            resource_type,
            reference.ref_name,
        )
    return reference_map


def _compact_relation_alias_by_name(analysis: dict[str, Any]) -> dict[str, str | None]:
    alias_by_name: dict[str, str | None] = {}
    relation_key: str
    for relation_key in (_POLYGLOT_ANALYSIS_RELATIONS, _POLYGLOT_ANALYSIS_BASE_TABLES):
        relations: object = analysis.get(relation_key)
        if not isinstance(relations, list):
            continue
        relation: object
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            name: object = relation.get(_POLYGLOT_ANALYSIS_NAME)
            if not isinstance(name, str) or not name:
                continue
            alias: object = relation.get(_POLYGLOT_PAYLOAD_ALIAS)
            alias_by_name[name] = alias if isinstance(alias, str) and alias else None
    return alias_by_name


def _compact_analysis_has_star(analysis: dict[str, Any]) -> bool:
    star_projections: object = analysis.get(_POLYGLOT_ANALYSIS_STAR_PROJECTIONS)
    return isinstance(star_projections, list) and bool(star_projections)


def _compact_projection_type(projection: dict[str, Any]) -> str | None:
    cast_type: object = projection.get(_POLYGLOT_ANALYSIS_CAST_TYPE)
    if isinstance(cast_type, str) and cast_type and cast_type != UNKNOWN_SQL_TYPE_NAME:
        return cast_type
    type_hint: object = projection.get(_POLYGLOT_ANALYSIS_TYPE_HINT)
    if isinstance(type_hint, str) and type_hint and type_hint != UNKNOWN_SQL_TYPE_NAME:
        return type_hint
    return None


def _compact_projection_nullability(
    *,
    projection: dict[str, Any],
    infer_nullability: bool,
) -> InferredNullability:
    if not infer_nullability:
        return InferredNullability.UNKNOWN
    value: object = projection.get(_POLYGLOT_ANALYSIS_NULLABILITY)
    if value == _POLYGLOT_ANALYSIS_NULLABILITY_NON_NULL:
        return InferredNullability.NON_NULL
    if value == _POLYGLOT_ANALYSIS_NULLABILITY_NULLABLE:
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN


def _compact_lineage_upstream_columns(
    *,
    projection: dict[str, Any],
    reference_map: dict[str, tuple[CompiledResourceType, str]],
    relation_alias_by_name: dict[str, str | None],
) -> tuple[tuple[CompiledLineageSourceFact, ...], ColumnLineageConfidence]:
    upstream_values: object = projection.get(_POLYGLOT_ANALYSIS_UPSTREAM)
    if not isinstance(upstream_values, list):
        return (), ColumnLineageConfidence.UNKNOWN
    columns: list[CompiledLineageSourceFact] = []
    seen: set[tuple[CompiledResourceType, str, str]] = set()
    confidence: ColumnLineageConfidence = ColumnLineageConfidence.HIGH
    upstream: object
    for upstream in upstream_values:
        if not isinstance(upstream, dict):
            continue
        column_name: object = upstream.get(_POLYGLOT_PAYLOAD_COLUMN)
        if not isinstance(column_name, str) or not column_name or column_name == SQL_WILDCARD_TOKEN:
            continue
        source_name: object = upstream.get(_POLYGLOT_ANALYSIS_SOURCE_NAME) or upstream.get(
            _POLYGLOT_ANALYSIS_TABLE
        )
        if not isinstance(source_name, str) or not source_name:
            confidence = ColumnLineageConfidence.UNKNOWN
            continue
        resource: tuple[CompiledResourceType, str] | None = reference_map.get(source_name)
        if resource is None:
            continue
        source_confidence: object = upstream.get(_POLYGLOT_ANALYSIS_SOURCE_CONFIDENCE)
        source_alias: object = upstream.get(_POLYGLOT_ANALYSIS_SOURCE_ALIAS)
        if source_confidence != RESOLVED_SOURCE_CONFIDENCE and not isinstance(source_alias, str):
            confidence = ColumnLineageConfidence.MEDIUM
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
    return tuple(
        sorted(
            columns,
            key=lambda column: (
                column.resource_type.value,
                column.resource_name,
                column.column_name,
            ),
        )
    ), confidence


def _compact_transform_kind(
    *, projection: dict[str, Any], has_upstream: bool
) -> ColumnTransformKind:
    transform_kind: str = str(projection.get(_POLYGLOT_ANALYSIS_TRANSFORM_KIND) or "")
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_STAR:
        return ColumnTransformKind.STAR
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_CAST:
        return ColumnTransformKind.CAST
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_AGGREGATION:
        return ColumnTransformKind.AGGREGATION
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_CONSTANT or not has_upstream:
        return ColumnTransformKind.CONSTANT
    if transform_kind == _POLYGLOT_ANALYSIS_TRANSFORM_DIRECT:
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION


def _infer_columns_with_polyglot(
    *,
    cleaned_sql: str,
    dialect: str | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> tuple[InferredColumn, ...] | None | bool:
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        _warn_once_polyglot_module_missing()
        return False
    try:
        parsed: Any = polyglot_module.parse_one(cleaned_sql, dialect=dialect or "generic")
    except Exception as error:
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
        try:
            select = parsed.find(_POLYGLOT_KIND_SELECT)
        except Exception as error:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="column inference select lookup failed; falling back",
                sqlbuild_error=str(error),
            )
            return None
    if select is None or str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return None

    column_nullability_by_table = dict(column_nullability_by_table)
    alias_nullability: dict[str, InferredNullability] = {}
    if _has_known_nullability(column_nullability_by_table):
        alias_nullability = _polyglot_alias_nullability_from_select(
            select=select,
            column_nullability_by_table=column_nullability_by_table,
        )
    columns: list[InferredColumn] = []
    projection: Any
    for projection in getattr(select, "expressions", ()):
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
        col_type: str | None = _polyglot_cast_type(inner)
        nullability: InferredNullability = InferredNullability.UNKNOWN
        if infer_nullability:
            nullability = _infer_polyglot_nullability(
                expression=inner,
                alias_nullability=alias_nullability,
                column_nullability_by_table=column_nullability_by_table,
                inference_profile=inference_profile,
            )
        columns.append(InferredColumn(name=name, type=col_type, nullability=nullability))
    return tuple(columns)


def _analyze_columns_and_lineage_from_polyglot_ast(
    *,
    parsed: Any,
    references: tuple[CompileSqlReference, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool]:
    infer_nullability: bool = str(getattr(parsed, "kind", "")) not in _POLYGLOT_SET_OPERATION_KINDS
    select: Any | None = parsed
    if str(getattr(select, "kind", "")) != _POLYGLOT_KIND_SELECT:
        try:
            select = parsed.find(_POLYGLOT_KIND_SELECT)
        except Exception as error:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="column lineage select lookup failed; falling back",
                sqlbuild_error=str(error),
            )
            return None, (), False
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

    columns: list[InferredColumn] = []
    lineage_columns: list[CompiledLineageColumnFact] = []
    has_star: bool = False
    projection: Any
    for projection in getattr(select, "expressions", ()):
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
        col_type: str | None = _polyglot_cast_type(inner)
        nullability: InferredNullability = InferredNullability.UNKNOWN
        if infer_nullability:
            nullability = (
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


def _extract_polyglot_lineage_facts(
    *,
    parsed: Any,
    references: tuple[CompileSqlReference, ...],
) -> tuple[tuple[CompiledLineageColumnFact, ...], bool]:
    if str(getattr(parsed, "kind", "")) != _POLYGLOT_KIND_SELECT:
        return (), False
    alias_map: dict[str, tuple[CompiledResourceType, str]] = _polyglot_reference_alias_map(
        parsed=parsed,
        references=references,
    )
    unqualified_resource: tuple[CompiledResourceType, str] | None = _single_alias_resource(
        alias_map
    )
    lineage_columns: list[CompiledLineageColumnFact] = []
    has_star: bool = False
    projection: Any
    for projection in getattr(parsed, "expressions", ()):
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
    return tuple(lineage_columns), has_star


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
    try:
        tables: tuple[Any, ...] = tuple(parsed.find_all(_POLYGLOT_KIND_TABLE))
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column lineage table discovery failed; falling back",
            sqlbuild_error=str(error),
        )
        return alias_map
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
    try:
        payload: object = expression.to_dict()
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column lineage expression payload extraction failed; falling back",
            sqlbuild_error=str(error),
        )
        return ()
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
    try:
        nodes: tuple[Any, ...] = tuple(expression.walk())
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column lineage aggregation detection failed; falling back",
            sqlbuild_error=str(error),
        )
        return False
    return any(str(getattr(node, "kind", "")) in _POLYGLOT_AGGREGATE_KINDS for node in nodes)


def _polyglot_cast_type(expression: Any) -> str | None:
    kind: str = str(getattr(expression, "kind", ""))
    if kind not in _POLYGLOT_CAST_KINDS:
        return None
    try:
        payload: object = expression.to_dict().get(kind, {})
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="column inference cast type extraction failed; falling back",
            sqlbuild_error=str(error),
        )
        return None
    if not isinstance(payload, dict):
        return None
    target: object = payload.get(_POLYGLOT_PAYLOAD_TO)
    if not isinstance(target, dict):
        return None
    raw_type: object = target.get(_POLYGLOT_PAYLOAD_DATA_TYPE)
    if not isinstance(raw_type, str) or not raw_type:
        return None
    type_name: str = _polyglot_type_name(raw_type)
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
    try:
        payload: object = expression.to_dict().get(_POLYGLOT_PAYLOAD_COLUMN, {})
    except Exception:
        payload = {}
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


def _polyglot_columns_in_expression(expression: Any) -> tuple[Any, ...]:
    if str(getattr(expression, "kind", "")) == _POLYGLOT_KIND_COLUMN:
        return (expression,)
    columns: list[Any] = []
    seen: set[int] = set()

    def visit(*, node: Any, visited: set[int], found: list[Any]) -> tuple[set[int], list[Any]]:
        node_id: int = id(node)
        if node_id in visited:
            return visited, found
        visited = visited | {node_id}
        if str(getattr(node, "kind", "")) == _POLYGLOT_KIND_COLUMN:
            return visited, [*found, node]
        for child in _polyglot_child_expressions(node):
            visited, found = visit(node=child, visited=visited, found=found)
        return visited, found

    seen, columns = visit(node=expression, visited=seen, found=columns)
    return tuple(columns)


def _polyglot_column_table_name(column: Any) -> str:
    try:
        payload: object = column.to_dict().get(_POLYGLOT_PAYLOAD_COLUMN, {})
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    table_payload: object = payload.get(_POLYGLOT_PAYLOAD_TABLE)
    if not isinstance(table_payload, dict):
        return ""
    raw_name: object = table_payload.get(_POLYGLOT_PAYLOAD_NAME)
    return raw_name if isinstance(raw_name, str) else ""


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

    try:
        select_payload: object = select.to_dict().get(_POLYGLOT_PAYLOAD_SELECT, {})
    except Exception:
        select_payload = {}
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


def _polyglot_table_alias_or_name(table: Any) -> str:
    alias_or_name: str = str(getattr(table, "alias_or_name", "") or "")
    if alias_or_name:
        return alias_or_name
    return str(getattr(table, "name", "") or "")


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


def _replace_refs_with_stubs(query_sql: str) -> str:
    """Replace SQLBuild marker calls with parseable SQL stubs."""

    result: str = _REF_PATTERN.sub(r"\1", query_sql)
    result = _SEED_PATTERN.sub(r"\1", result)
    result = _SOURCE_PATTERN.sub(r"\1", result)
    result = _DBT_REF_PATTERN.sub(r"\1", result)
    result = _UDF_PATTERN.sub(r"__sqlbuild_udf_\1", result)
    result = _replace_table_function_calls_with_stubs(result)
    return result


def _replace_table_function_calls_with_stubs(query_sql: str) -> str:
    parts: list[str] = []
    last_index: int = 0
    match: re.Match[str]
    for match in _TABLE_FUNCTION_PATTERN.finditer(query_sql):
        parts.append(query_sql[last_index : match.start()])
        call_end: int = find_matching_paren(
            sql=query_sql,
            open_paren_index=match.end(),
            context="SQL table function analysis",
        )
        parts.append(table_function_analysis_name(match.group(1)))
        last_index = call_end + 1
    parts.append(query_sql[last_index:])
    return "".join(parts)


def _find_outermost_select(*, parsed: Any, expressions_module: Any) -> Any | None:
    """Find the outermost SELECT statement from a parsed expression."""

    union_type: type[Any] = expressions_module.Union
    select_type: type[Any] = expressions_module.Select
    intersect_type: type[Any] = expressions_module.Intersect
    except_type: type[Any] = expressions_module.Except

    if isinstance(parsed, (union_type, intersect_type, except_type)):
        return parsed.find(select_type)
    if isinstance(parsed, select_type):
        return parsed

    body: Any | None = getattr(parsed, "this", None)
    if body is None:
        return None
    if isinstance(body, (union_type, intersect_type, except_type)):
        return body.find(select_type)
    if isinstance(body, select_type):
        return body
    return parsed.find(select_type)


def _is_set_operation(*, parsed: Any, expressions_module: Any) -> bool:
    union_type: type[Any] = expressions_module.Union
    intersect_type: type[Any] = expressions_module.Intersect
    except_type: type[Any] = expressions_module.Except
    if isinstance(parsed, (union_type, intersect_type, except_type)):
        return True
    body: Any | None = getattr(parsed, "this", None)
    return isinstance(body, (union_type, intersect_type, except_type))


def _extract_columns_from_select(
    *,
    select: Any,
    expressions_module: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    infer_nullability: bool,
    inference_profile: ExpressionInferenceProfile,
) -> tuple[InferredColumn, ...]:
    """Extract output column names and types from a SELECT's projection list."""

    column_nullability_by_table = dict(column_nullability_by_table)
    star_type: type[Any] = expressions_module.Star
    alias_type: type[Any] = expressions_module.Alias
    column_type: type[Any] = expressions_module.Column
    cast_type: type[Any] = expressions_module.Cast
    try_cast_type: type[Any] = expressions_module.TryCast
    alias_nullability: dict[str, InferredNullability] = _alias_nullability_from_select(
        select=select,
        expressions_module=expressions_module,
        column_nullability_by_table=column_nullability_by_table,
    )

    projection_list: list[Any] = select.args.get("expressions", [])
    columns: list[InferredColumn] = []

    expression: Any
    for expression in projection_list:
        if isinstance(expression, star_type):
            continue

        name: str
        inner: Any
        if isinstance(expression, alias_type):
            name = expression.alias
            inner = expression.this
        elif isinstance(expression, column_type):
            name = expression.name
            inner = expression
        else:
            continue

        col_type: str | None = None
        if isinstance(inner, (cast_type, try_cast_type)):
            col_type = inner.to.sql()

        nullability: InferredNullability = InferredNullability.UNKNOWN
        if infer_nullability:
            nullability = _infer_expression_nullability(
                expression=inner,
                expressions_module=expressions_module,
                alias_nullability=alias_nullability,
                column_nullability_by_table=column_nullability_by_table,
                inference_profile=inference_profile,
            )

        columns.append(InferredColumn(name=name, type=col_type, nullability=nullability))

    return tuple(columns)


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


def _alias_nullability_from_select(
    *,
    select: Any,
    expressions_module: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> dict[str, InferredNullability]:
    table_type: type[Any] = expressions_module.Table
    alias_nullability: dict[str, InferredNullability] = {}
    current_aliases: set[str] = set()

    from_expression: Any | None = select.args.get("from_")
    from_table: Any | None = getattr(from_expression, "this", None)
    if isinstance(from_table, table_type):
        alias: str = _table_alias_or_name(from_table)
        current_aliases.add(alias)
        alias_nullability[alias] = InferredNullability.UNKNOWN
        _copy_table_facts_to_alias(
            alias=alias,
            table_name=from_table.name,
            column_nullability_by_table=column_nullability_by_table,
        )

    for join in select.args.get("joins") or []:
        joined_table: Any | None = join.this
        if not isinstance(joined_table, table_type):
            continue
        joined_alias: str = _table_alias_or_name(joined_table)
        side: str = str(join.args.get("side") or "").upper()
        if side == LEFT_JOIN_SIDE:
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        elif side == RIGHT_JOIN_SIDE:
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        elif side == FULL_JOIN_SIDE:
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        else:
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        current_aliases.add(joined_alias)
        _copy_table_facts_to_alias(
            alias=joined_alias,
            table_name=joined_table.name,
            column_nullability_by_table=column_nullability_by_table,
        )
    return alias_nullability


def _table_alias_or_name(table: Any) -> str:
    return str(table.alias_or_name or table.name)


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
