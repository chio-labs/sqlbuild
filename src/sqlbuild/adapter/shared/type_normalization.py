"""Shared type normalization helpers for adapter comparisons."""

from __future__ import annotations

import re
from typing import Any

from sqlbuild.adapter.shared.constants import (
    BOOLEAN_TYPE_NAMES,
    DECIMAL_TYPE_NAMES,
    FLOAT_TYPE_NAMES,
    INTEGER_TYPE_NAMES,
    STRING_TYPE_NAMES,
    TIMESTAMP_TYPE_NAMES,
)
from sqlbuild.adapter.shared.models import NormalizedType
from sqlbuild.adapter.shared.types import TypeDialect, TypeFamily
from sqlbuild.shared.helpers.sqlglot import import_sqlglot, import_sqlglot_expressions


def normalize_type(*, type_sql: str, dialect: TypeDialect | str | None) -> NormalizedType:
    """Normalize one warehouse type string into a semantic comparison shape."""

    sqlglot_normalized: NormalizedType | None = _normalize_with_sqlglot(
        type_sql=type_sql,
        dialect=dialect,
    )
    if sqlglot_normalized is not None:
        return sqlglot_normalized
    return _normalize_with_fallback(type_sql=type_sql, dialect=dialect)


def normalize_numeric_family(*, type_sql: str, dialect: TypeDialect | str | None) -> str | None:
    """Return the normalized numeric family for one type, if numeric."""

    family: TypeFamily = normalize_type(type_sql=type_sql, dialect=dialect).family
    if family in {TypeFamily.INTEGER, TypeFamily.DECIMAL, TypeFamily.FLOAT}:
        return family
    return None


def types_equal(*, left: str, right: str, dialect: TypeDialect | str | None) -> bool:
    """Return whether two type strings are semantically equivalent."""

    return normalize_type(type_sql=left, dialect=dialect) == normalize_type(
        type_sql=right,
        dialect=dialect,
    )


def _normalize_with_sqlglot(
    *, type_sql: str, dialect: TypeDialect | str | None
) -> NormalizedType | None:
    sqlglot_module: Any | None = import_sqlglot()
    expressions_module: Any | None = import_sqlglot_expressions()
    if sqlglot_module is None or expressions_module is None:
        return None
    try:
        parsed: Any = sqlglot_module.parse_one(
            type_sql,
            read=dialect,
            into=expressions_module.DataType,
        )
    except Exception:
        return None
    return _normalized_from_parsed_type(parsed=parsed, dialect=dialect)


def _normalized_from_parsed_type(
    *, parsed: Any, dialect: TypeDialect | str | None
) -> NormalizedType:
    normalized_dialect: TypeDialect | None = _coerce_type_dialect(dialect)
    normalized_name: str = parsed.sql(dialect=dialect).upper().replace(" ", "")
    dtype_name: str = str(parsed.this).upper().removeprefix("DTYPE.")
    expressions: list[Any] = list(getattr(parsed, "expressions", []) or [])
    params: list[int] = [_data_type_param_to_int(expression) for expression in expressions]

    if normalized_dialect == TypeDialect.BIGQUERY and dtype_name in {"INT", "BIGINT"}:
        normalized_name = "INT64"
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.INTEGER)
    if dtype_name in INTEGER_TYPE_NAMES:
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.INTEGER)
    if dtype_name in DECIMAL_TYPE_NAMES:
        precision: int | None = params[0] if len(params) >= 1 else None
        scale: int | None = params[1] if len(params) >= 2 else None
        return NormalizedType(
            normalized_name=normalized_name,
            family=TypeFamily.DECIMAL,
            precision=precision,
            scale=scale,
        )
    if dtype_name in FLOAT_TYPE_NAMES:
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.FLOAT)
    if dtype_name in STRING_TYPE_NAMES:
        length: int | None = params[0] if len(params) >= 1 else None
        return NormalizedType(
            normalized_name=normalized_name,
            family=TypeFamily.STRING,
            length=length,
        )
    if dtype_name in BOOLEAN_TYPE_NAMES:
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.BOOLEAN)
    if dtype_name in TIMESTAMP_TYPE_NAMES:
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.TIMESTAMP)
    if dtype_name == "DATE":
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.DATE)
    if dtype_name == "DATETIME":
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.DATETIME)
    return NormalizedType(normalized_name=normalized_name, family=TypeFamily.OTHER)


def _normalize_with_fallback(*, type_sql: str, dialect: TypeDialect | str | None) -> NormalizedType:
    normalized_dialect: TypeDialect | None = _coerce_type_dialect(dialect)
    normalized: str = type_sql.upper().strip()
    normalized = re.sub(r"\s+", "", normalized)
    base_type, params = _split_type_and_params(normalized)

    if base_type in INTEGER_TYPE_NAMES:
        normalized_name: str = _fallback_integer_normalized_name(
            base_type=base_type,
            dialect=normalized_dialect,
        )
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.INTEGER)
    if base_type in DECIMAL_TYPE_NAMES:
        precision: int | None = params[0] if len(params) >= 1 else None
        scale: int | None = params[1] if len(params) >= 2 else None
        normalized_name = _fallback_decimal_normalized_name(
            base_type=base_type,
            dialect=normalized_dialect,
        )
        if precision is not None and scale is not None:
            normalized_name = f"{normalized_name}({precision},{scale})"
        elif precision is not None:
            normalized_name = f"{normalized_name}({precision})"
        return NormalizedType(
            normalized_name=normalized_name,
            family=TypeFamily.DECIMAL,
            precision=precision,
            scale=scale,
        )
    if base_type in FLOAT_TYPE_NAMES:
        normalized_name = _fallback_float_normalized_name(
            base_type=base_type,
            dialect=normalized_dialect,
        )
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.FLOAT)
    if base_type in STRING_TYPE_NAMES:
        length: int | None = params[0] if len(params) >= 1 else None
        normalized_name = _fallback_string_normalized_name(
            base_type=base_type,
            dialect=normalized_dialect,
        )
        normalized_name = normalized_name if length is None else f"{normalized_name}({length})"
        return NormalizedType(
            normalized_name=normalized_name,
            family=TypeFamily.STRING,
            length=length,
        )
    if base_type in BOOLEAN_TYPE_NAMES:
        normalized_name = _fallback_boolean_normalized_name(
            base_type=base_type,
            dialect=normalized_dialect,
        )
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.BOOLEAN)
    if "TIMESTAMP" in base_type:
        return NormalizedType(normalized_name=base_type, family=TypeFamily.TIMESTAMP)
    if base_type == "DATE":
        return NormalizedType(normalized_name=base_type, family=TypeFamily.DATE)
    if base_type == "DATETIME":
        return NormalizedType(normalized_name=base_type, family=TypeFamily.DATETIME)
    return NormalizedType(normalized_name=normalized, family=TypeFamily.OTHER)


def _split_type_and_params(type_sql: str) -> tuple[str, list[int]]:
    match: re.Match[str] | None = re.match(r"^([A-Z0-9_]+)(?:\(([^)]*)\))?$", type_sql)
    if match is None:
        return type_sql, []
    raw_params: str | None = match.group(2)
    if raw_params is None or not raw_params:
        return match.group(1), []
    params: list[int] = []
    raw_part: str
    for raw_part in raw_params.split(","):
        try:
            params.append(int(raw_part.strip()))
        except ValueError:
            continue
    return match.group(1), params


def _fallback_integer_normalized_name(*, base_type: str, dialect: TypeDialect | None) -> str:
    if dialect == TypeDialect.BIGQUERY:
        return "INT64"
    return base_type


def _fallback_decimal_normalized_name(*, base_type: str, dialect: TypeDialect | None) -> str:
    if dialect == TypeDialect.BIGQUERY:
        if base_type == "BIGNUMERIC":
            return "BIGNUMERIC"
        return "NUMERIC"
    return base_type


def _fallback_float_normalized_name(*, base_type: str, dialect: TypeDialect | None) -> str:
    if dialect == TypeDialect.BIGQUERY:
        return "FLOAT64"
    return base_type


def _fallback_string_normalized_name(*, base_type: str, dialect: TypeDialect | None) -> str:
    if dialect == TypeDialect.BIGQUERY:
        return "STRING"
    if dialect == TypeDialect.SNOWFLAKE and base_type == "TEXT":
        return "VARCHAR"
    return base_type


def _fallback_boolean_normalized_name(*, base_type: str, dialect: TypeDialect | None) -> str:
    if dialect == TypeDialect.BIGQUERY:
        return "BOOL"
    return base_type


def _data_type_param_to_int(expression: Any) -> int:
    literal: Any = getattr(expression, "this", None)
    return int(str(getattr(literal, "this", literal)))


def _coerce_type_dialect(dialect: TypeDialect | str | None) -> TypeDialect | None:
    if isinstance(dialect, TypeDialect):
        return dialect
    if dialect is None:
        return None
    try:
        return TypeDialect(dialect)
    except ValueError:
        return None
