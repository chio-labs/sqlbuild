"""Shared type normalization helpers for adapter comparisons."""

from __future__ import annotations

import logging
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
from sqlbuild.shared.helpers.diagnostics.logging import log_debug_event
from sqlbuild.shared.helpers.sql.polyglot import import_polyglot

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.adapter")


def normalize_type(*, type_sql: str, dialect: TypeDialect | str | None) -> NormalizedType:
    """Normalize one warehouse type string into a semantic comparison shape."""

    polyglot_normalized: NormalizedType | None = _normalize_with_polyglot(
        type_sql=type_sql,
        dialect=dialect,
    )
    if polyglot_normalized is not None:
        return polyglot_normalized
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


def _normalize_with_polyglot(
    *, type_sql: str, dialect: TypeDialect | str | None
) -> NormalizedType | None:
    polyglot_module: Any | None = import_polyglot()
    if polyglot_module is None:
        return None
    try:
        parsed: Any = polyglot_module.parse_data_type(type_sql, dialect=dialect or "generic")
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="type normalization polyglot parse failed; falling back",
            type_sql=type_sql,
            dialect=str(dialect),
            sqlbuild_error=str(error),
        )
        return None
    return _normalized_from_parsed_type(parsed=parsed, dialect=dialect)


def _normalized_from_parsed_type(
    *, parsed: Any, dialect: TypeDialect | str | None
) -> NormalizedType:
    normalized_dialect: TypeDialect | None = _coerce_type_dialect(dialect)
    normalized_name: str = parsed.sql(dialect=dialect or "generic").upper().replace(" ", "")
    args: dict[str, Any] = dict(getattr(parsed, "args", {}) or {})
    dtype_name: str = _polyglot_type_name(args=args)
    params: list[int] = _polyglot_type_params(args=args)
    precision_and_scale_count: int = 2

    if normalized_dialect == TypeDialect.BIGQUERY and dtype_name in {"INT", "BIGINT"}:
        normalized_name = "INT64"
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.INTEGER)
    if normalized_dialect == TypeDialect.BIGQUERY and dtype_name == "BIGNUMERIC":
        return NormalizedType(normalized_name="BIGNUMERIC", family=TypeFamily.DECIMAL)
    if normalized_dialect == TypeDialect.BIGQUERY and dtype_name == "FLOAT64":
        return NormalizedType(normalized_name="FLOAT64", family=TypeFamily.FLOAT)
    if dtype_name == "CUSTOM":
        raw_name: str = str(args.get("name", normalized_name)).upper().replace(" ", "")
        if normalized_dialect == TypeDialect.SNOWFLAKE and raw_name.startswith("NUMBER"):
            decimal_name: str = raw_name.replace("NUMBER", "DECIMAL", 1)
            base_type, params = _split_type_and_params(decimal_name)
            precision: int | None = params[0] if len(params) >= 1 else None
            scale: int | None = params[1] if len(params) >= precision_and_scale_count else None
            return NormalizedType(
                normalized_name=base_type if not params else decimal_name,
                family=TypeFamily.DECIMAL,
                precision=precision,
                scale=scale,
            )
        return _normalize_with_fallback(type_sql=raw_name, dialect=dialect)
    if dtype_name in INTEGER_TYPE_NAMES:
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.INTEGER)
    if dtype_name in DECIMAL_TYPE_NAMES:
        precision: int | None = params[0] if len(params) >= 1 else None
        scale: int | None = params[1] if len(params) >= precision_and_scale_count else None
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
        normalized_name = _timestamp_normalized_name(
            normalized_name=normalized_name,
            dialect=normalized_dialect,
        )
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
    precision_and_scale_count: int = 2

    if base_type in INTEGER_TYPE_NAMES:
        normalized_name: str = _fallback_integer_normalized_name(
            base_type=base_type,
            dialect=normalized_dialect,
        )
        return NormalizedType(normalized_name=normalized_name, family=TypeFamily.INTEGER)
    if base_type in DECIMAL_TYPE_NAMES:
        precision: int | None = params[0] if len(params) >= 1 else None
        scale: int | None = params[1] if len(params) >= precision_and_scale_count else None
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
        normalized_timestamp_name: str = _timestamp_normalized_name(
            normalized_name=base_type,
            dialect=normalized_dialect,
        )
        return NormalizedType(
            normalized_name=normalized_timestamp_name,
            family=TypeFamily.TIMESTAMP,
        )
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


def _timestamp_normalized_name(*, normalized_name: str, dialect: TypeDialect | None) -> str:
    if dialect != TypeDialect.SNOWFLAKE:
        return normalized_name
    compact: str = normalized_name.replace("_", "")
    if compact in {"TIMESTAMP", "TIMESTAMPNTZ"}:
        return "TIMESTAMP_NTZ"
    if compact == "TIMESTAMPLTZ":
        return "TIMESTAMP_LTZ"
    if compact == "TIMESTAMPTZ":
        return "TIMESTAMP_TZ"
    return normalized_name


def _polyglot_type_name(*, args: dict[str, Any]) -> str:
    data_type: str = str(args.get("data_type", "")).upper()
    polyglot_name_map: dict[str, str] = {
        "BIG_INT": "BIGINT",
        "SMALL_INT": "SMALLINT",
        "TINY_INT": "TINYINT",
        "VAR_CHAR": "VARCHAR",
        "TEXT": "TEXT",
        "INT": "INT",
        "BOOLEAN": "BOOLEAN",
        "DECIMAL": "DECIMAL",
        "DOUBLE": "DOUBLE",
        "FLOAT": "FLOAT",
        "TIMESTAMP": "TIMESTAMP",
        "DATE": "DATE",
        "DATETIME": "DATETIME",
    }
    mapped_name: str | None = polyglot_name_map.get(data_type)
    if mapped_name is not None:
        return mapped_name
    if data_type == "CUSTOM":
        name: str = str(args.get("name", "")).upper().replace(" ", "")
        if name in {"INT64", "FLOAT64", "BIGNUMERIC"}:
            return name
    return data_type


def _polyglot_type_params(*, args: dict[str, Any]) -> list[int]:
    params: list[int] = []
    key: str
    for key in ("precision", "scale", "length"):
        value: Any = args.get(key)
        if value is None:
            continue
        try:
            params.append(int(value))
        except (TypeError, ValueError):
            continue
    return params


def _coerce_type_dialect(dialect: TypeDialect | str | None) -> TypeDialect | None:
    if isinstance(dialect, TypeDialect):
        return dialect
    if dialect is None:
        return None
    try:
        return TypeDialect(dialect)
    except ValueError:
        return None
