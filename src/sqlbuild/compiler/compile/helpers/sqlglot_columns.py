"""Optional SQLGlot-backed output column inference from model query SQL."""

from __future__ import annotations

import re
from typing import Any, cast

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.adapter.shared.types import FunctionNullabilityRule
from sqlbuild.compiler.compile.models.core import (
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.shared.helpers.polyglot import import_polyglot_sql
from sqlbuild.shared.helpers.sql_reference_patterns import (
    quoted_reference_call_pattern,
    reference_call_prefix_pattern_text,
)
from sqlbuild.shared.helpers.sqlglot import import_sqlglot, import_sqlglot_expressions
from sqlbuild.shared.types import SqlReferenceKind

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


def infer_columns_with_sqlglot(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> tuple[InferredColumn, ...] | None:
    """Infer output columns from model query SQL using SQLGlot.

    Returns None if SQLGlot is not available or the SQL cannot be parsed.
    Returns an empty tuple if the outermost SELECT uses SELECT * with no
    extractable column names.
    """

    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)

    polyglot_columns: tuple[InferredColumn, ...] | None | bool = _infer_columns_with_polyglot(
        cleaned_sql=cleaned_sql,
        dialect=profile.sqlglot_dialect,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )
    if isinstance(polyglot_columns, tuple):
        return polyglot_columns

    sqlglot_module: Any | None = import_sqlglot()
    expressions_module: Any | None = import_sqlglot_expressions()
    if sqlglot_module is None or expressions_module is None:
        return None

    try:
        parsed: Any = sqlglot_module.parse_one(cleaned_sql, dialect=profile.sqlglot_dialect)
    except Exception:
        return None

    infer_nullability: bool = not _is_set_operation(
        parsed=parsed, expressions_module=expressions_module
    )
    select: Any | None = _find_outermost_select(
        parsed=parsed, expressions_module=expressions_module
    )
    if select is None:
        return None

    return _extract_columns_from_select(
        select=select,
        expressions_module=expressions_module,
        column_nullability_by_table=column_nullability_by_table or {},
        infer_nullability=infer_nullability,
        inference_profile=profile,
    )


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
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)
    return _infer_columns_with_polyglot(
        cleaned_sql=cleaned_sql,
        dialect=profile.sqlglot_dialect,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )


def analyze_columns_and_lineage_with_polyglot(
    *,
    query_sql: str,
    references: tuple[CompileSqlReference, ...] = (),
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> tuple[tuple[InferredColumn, ...] | None, tuple[CompiledLineageColumnFact, ...], bool] | bool:
    """Infer columns and compact lineage facts from one Polyglot parse."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return False
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()
    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)
    try:
        parsed: Any = polyglot_module.parse_one(
            cleaned_sql,
            dialect=profile.sqlglot_dialect or "generic",
        )
    except Exception:
        return False
    columns: tuple[InferredColumn, ...] | None | bool = _infer_columns_from_polyglot_ast(
        parsed=parsed,
        column_nullability_by_table=column_nullability_by_table or {},
        inference_profile=profile,
    )
    if columns is False:
        return False
    if columns is True:
        return False
    lineage_columns, has_star = _extract_polyglot_lineage_facts(
        parsed=parsed,
        references=references,
    )
    return columns, lineage_columns, has_star


def _infer_columns_with_polyglot(
    *,
    cleaned_sql: str,
    dialect: str | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> tuple[InferredColumn, ...] | None | bool:
    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return False
    try:
        parsed: Any = polyglot_module.parse_one(cleaned_sql, dialect=dialect or "generic")
    except Exception:
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
    infer_nullability: bool = str(getattr(parsed, "kind", "")) not in {
        "union",
        "intersect",
        "except",
    }
    select: Any | None = parsed
    if str(getattr(select, "kind", "")) != "select":
        try:
            select = parsed.find("select")
        except Exception:
            return None
    if select is None or str(getattr(select, "kind", "")) != "select":
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
        if not name or name == "*":
            continue
        inner: Any = (
            projection.this if str(getattr(projection, "kind", "")) == "alias" else projection
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


def _extract_polyglot_lineage_facts(
    *,
    parsed: Any,
    references: tuple[CompileSqlReference, ...],
) -> tuple[tuple[CompiledLineageColumnFact, ...], bool]:
    if str(getattr(parsed, "kind", "")) != "select":
        return (), False
    alias_map: dict[str, tuple[CompiledResourceType, str]] = _polyglot_reference_alias_map(
        parsed=parsed,
        references=references,
    )
    lineage_columns: list[CompiledLineageColumnFact] = []
    has_star: bool = False
    projection: Any
    for projection in getattr(parsed, "expressions", ()):
        if bool(getattr(projection, "is_star", False)):
            has_star = True
            continue
        inner: Any = (
            projection.this if str(getattr(projection, "kind", "")) == "alias" else projection
        )
        if bool(getattr(inner, "is_star", False)):
            has_star = True
            continue
        output_column: str = str(getattr(projection, "output_name", "") or "")
        if not output_column or output_column == "*":
            continue
        upstream_columns, confidence = _polyglot_lineage_upstream_columns(
            projection=projection,
            alias_map=alias_map,
        )
        transform_kind: ColumnTransformKind = _polyglot_lineage_transform_kind(
            inner,
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
        resource_by_name[reference.ref_name] = (resource_type, reference.ref_name)
    alias_map: dict[str, tuple[CompiledResourceType, str]] = {}
    try:
        tables: tuple[Any, ...] = tuple(parsed.find_all("table"))
    except Exception:
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
    return None


def _polyglot_lineage_upstream_columns(
    *,
    projection: Any,
    alias_map: dict[str, tuple[CompiledResourceType, str]],
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
        elif len({resource_name for _, resource_name in alias_map.values()}) == 1:
            resource = next(iter(alias_map.values()))
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


def _polyglot_column_refs_in_expression(expression: Any) -> tuple[tuple[str, str], ...]:
    if str(getattr(expression, "kind", "")) == "column":
        return ((str(getattr(expression, "name", "") or ""), _polyglot_column_table_name(expression)),)
    try:
        payload: object = expression.to_dict()
    except Exception:
        return ()
    refs: list[tuple[str, str]] = []

    def visit(node: object) -> None:
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
                refs.append((column_name, table_name))
                return
            for value in node_dict.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(payload)
    return tuple(refs)


def _has_known_nullability(
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> bool:
    return any(
        value != InferredNullability.UNKNOWN
        for column_facts in column_nullability_by_table.values()
        for value in column_facts.values()
    )


def _polyglot_lineage_transform_kind(expression: Any, *, has_upstream: bool) -> ColumnTransformKind:
    kind: str = str(getattr(expression, "kind", ""))
    if bool(getattr(expression, "is_star", False)):
        return ColumnTransformKind.STAR
    if kind in {"cast", "try_cast"}:
        return ColumnTransformKind.CAST
    if _polyglot_has_aggregation(expression):
        return ColumnTransformKind.AGGREGATION
    if not has_upstream:
        return ColumnTransformKind.CONSTANT
    if kind == "column":
        return ColumnTransformKind.DIRECT
    return ColumnTransformKind.EXPRESSION


def _polyglot_has_aggregation(expression: Any) -> bool:
    aggregate_kinds: frozenset[str] = frozenset(
        {"avg", "count", "max", "min", "sum", "array_agg", "string_agg"}
    )
    try:
        nodes: tuple[Any, ...] = tuple(expression.walk())
    except Exception:
        return False
    return any(str(getattr(node, "kind", "")) in aggregate_kinds for node in nodes)


def _polyglot_cast_type(expression: Any) -> str | None:
    kind: str = str(getattr(expression, "kind", ""))
    if kind not in {"cast", "try_cast"}:
        return None
    try:
        payload: object = expression.to_dict().get(kind, {})
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    target: object = payload.get("to")
    if not isinstance(target, dict):
        return None
    raw_type: object = target.get("data_type")
    if not isinstance(raw_type, str) or not raw_type:
        return None
    type_name: str = _polyglot_type_name(raw_type)
    precision: object = target.get("precision")
    scale: object = target.get("scale")
    if type_name == "DECIMAL" and isinstance(precision, int):
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
    if kind == "null":
        return InferredNullability.NULLABLE
    if kind == "literal":
        return InferredNullability.NON_NULL
    if kind == "column":
        return _infer_polyglot_column_nullability(
            expression=expression,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
        )
    if kind == "cast":
        inner: Any | None = getattr(expression, "this", None)
        if inner is None:
            return InferredNullability.UNKNOWN
        return _infer_polyglot_nullability(
            expression=inner,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
    if kind == "try_cast":
        return InferredNullability.UNKNOWN
    if kind == "count":
        return InferredNullability.NON_NULL
    if kind == "coalesce":
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
        payload: object = expression.to_dict().get("column", {})
    except Exception:
        payload = {}
    table_name: str = ""
    if isinstance(payload, dict):
        table_payload: object = payload.get("table")
        if isinstance(table_payload, dict):
            raw_name: object = table_payload.get("name")
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
    if str(getattr(expression, "kind", "")) == "column":
        return (expression,)
    columns: list[Any] = []
    seen: set[int] = set()

    def visit(node: Any) -> None:
        node_id: int = id(node)
        if node_id in seen:
            return
        seen.add(node_id)
        if str(getattr(node, "kind", "")) == "column":
            columns.append(node)
            return
        for child in _polyglot_child_expressions(node):
            visit(child)

    visit(expression)
    return tuple(columns)


def _polyglot_column_table_name(column: Any) -> str:
    try:
        payload: object = column.to_dict().get("column", {})
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    table_payload: object = payload.get("table")
    if not isinstance(table_payload, dict):
        return ""
    raw_name: object = table_payload.get("name")
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
        select_payload: object = select.to_dict().get("select", {})
    except Exception:
        select_payload = {}
    if not isinstance(select_payload, dict):
        return alias_nullability

    from_payload: object = select_payload.get("from")
    if isinstance(from_payload, dict):
        from_expressions: object = from_payload.get("expressions")
        if isinstance(from_expressions, list) and len(from_expressions) == 1:
            from_table_payload: object = from_expressions[0]
            if isinstance(from_table_payload, dict):
                table_payload: object = from_table_payload.get("table")
                if isinstance(table_payload, dict):
                    alias, table_name = _polyglot_table_payload_alias_and_name(table_payload)
                    current_aliases.add(alias)
                    alias_nullability[alias] = InferredNullability.UNKNOWN
                    _copy_table_facts_to_alias(
                        alias=alias,
                        table_name=table_name,
                        column_nullability_by_table=column_nullability_by_table,
                    )

    joins_payload: object = select_payload.get("joins")
    if not isinstance(joins_payload, list):
        return alias_nullability
    for join_payload in joins_payload:
        if not isinstance(join_payload, dict):
            continue
        this_payload: object = join_payload.get("this")
        if not isinstance(this_payload, dict):
            continue
        joined_table_payload: object = this_payload.get("table")
        if not isinstance(joined_table_payload, dict):
            continue
        joined_alias, joined_table_name = _polyglot_table_payload_alias_and_name(
            joined_table_payload
        )
        side: str = str(join_payload.get("kind") or "").upper()
        if side == "LEFT":
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        elif side == "RIGHT":
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        elif side == "FULL":
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
    table_name: str = _polyglot_name_payload_value(table_payload.get("name"))
    alias: str = _polyglot_name_payload_value(table_payload.get("alias")) or table_name
    return alias, table_name


def _polyglot_name_payload_value(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        payload_dict: dict[str, object] = cast(dict[str, object], payload)
        name: object = payload_dict.get("name")
        if isinstance(name, str):
            return name
    return ""


def substitute_placeholder_defaults(query_sql: str, placeholders: dict[str, str]) -> str:
    """Replace @@@name tokens with their default values for SQLGlot parsing."""

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
    result = _TABLE_FUNCTION_PATTERN.sub(r"__sqlbuild_table_function_\1", result)
    return result


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
        if side == "LEFT":
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        elif side == "RIGHT":
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        elif side == "FULL":
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
        column_nullability_by_table.setdefault(alias, table_facts)
