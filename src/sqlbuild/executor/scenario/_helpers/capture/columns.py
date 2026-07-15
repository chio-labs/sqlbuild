"""Scenario snapshot column metadata helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.sql_analysis.main.import_polyglot import import_polyglot
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.scenario.constants import (
    BIGQUERY_BIGNUMERIC_TYPE,
    BIGQUERY_BYTES_TYPE,
    BIGQUERY_TIMESTAMP_TYPE,
    BIGQUERY_VARCHAR_TYPES,
    BIGQUERY_WIDEN_TO_DOUBLE_TYPES,
    DATABRICKS_TIMESTAMP_NTZ_TYPE,
    DATABRICKS_TIMESTAMP_TYPE,
    DATABRICKS_VOID_TYPE,
    DUCKDB_BLOB_TYPE,
    DUCKDB_HUGEINT_TYPE,
    DUCKDB_INTEGER_TYPE,
    DUCKDB_LIST_TYPE,
    DUCKDB_UHUGEINT_TYPE,
    FALLBACK_BINARY_TYPES,
    FALLBACK_BOOLEAN_TYPES,
    FALLBACK_DATE_TYPE,
    FALLBACK_DECIMAL_TYPES,
    FALLBACK_FLOAT_TYPES,
    FALLBACK_JSON_TYPES,
    FALLBACK_POLYGLOT_BASE_TYPES,
    FALLBACK_SIGNED_INTEGER_TYPES,
    FALLBACK_STRUCTURED_TYPES,
    FALLBACK_TIME_TYPES,
    FALLBACK_TIMESTAMP_TOKEN,
    FALLBACK_TIMESTAMP_TYPES,
    FALLBACK_UNSIGNED_INTEGER_TYPES,
    FALLBACK_VARCHAR_TYPES,
    GENERIC_WIDEN_TO_DOUBLE_TYPES,
    LOCAL_TYPE_BIGINT,
    LOCAL_TYPE_BOOLEAN,
    LOCAL_TYPE_DATE,
    LOCAL_TYPE_DECIMAL,
    LOCAL_TYPE_DOUBLE,
    LOCAL_TYPE_INT,
    LOCAL_TYPE_INT128,
    LOCAL_TYPE_JSON,
    LOCAL_TYPE_REAL,
    LOCAL_TYPE_SMALLINT,
    LOCAL_TYPE_TEXT,
    LOCAL_TYPE_TIME,
    LOCAL_TYPE_TIMESTAMP,
    LOCAL_TYPE_TIMESTAMPTZ,
    LOCAL_TYPE_UINT128,
    LOCAL_TYPE_VARCHAR,
    MALFORMED_RENDERED_TYPE_TOKEN,
    POLYGLOT_ARRAY_TYPE,
    POLYGLOT_COLLECTION_TYPES,
    POLYGLOT_CUSTOM_TYPE,
    POLYGLOT_DECIMAL_TYPES,
    POLYGLOT_OBJECT_TYPE,
    POLYGLOT_SPATIAL_AND_MONEY_TYPES,
    POLYGLOT_VARCHAR_TYPES,
    POSTGRES_BIGSERIAL_TYPE,
    POSTGRES_PARAMETERIZED_DECIMAL_TYPES,
    POSTGRES_PARAMETERIZED_TEXT_TYPES,
    POSTGRES_SERIAL_TYPES,
    POSTGRES_SMALLSERIAL_TYPE,
    POSTGRES_VARCHAR_TYPES,
    SCENARIO_LOCAL_TYPE_INVALID,
    SNOWFLAKE_DOUBLE_TYPES,
    SNOWFLAKE_NUMBER_TYPE,
    SNOWFLAKE_REAL_TYPE,
    SNOWFLAKE_TIMESTAMP_NTZ_TYPE,
    SNOWFLAKE_TIMEZONE_TIMESTAMP_TYPES,
    SNOWFLAKE_VECTOR_TYPE,
    SNOWFLAKE_WIDEN_TO_DOUBLE_TYPES,
    TYPE_ARGUMENT_CLOSE_ANGLE,
    TYPE_ARGUMENT_CLOSE_PAREN,
    TYPE_ARGUMENT_CLOSE_TOKENS,
    TYPE_ARGUMENT_OPEN_PAREN,
    TYPE_ARGUMENT_OPEN_TOKENS,
    TYPE_ARGUMENT_SEPARATOR,
    TYPE_PATTERN_WILDCARD,
    UNTYPED_ARRAY_TYPE,
)
from sqlbuild.executor.scenario.models import ScenarioSnapshotColumn

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


@dataclass(frozen=True)
class _TypePattern:
    base: str
    args: tuple[str, ...] = ()


_POSTGRES_DIRECT_LOCAL_TYPES: dict[str, str] = {
    "SMALLINT": LOCAL_TYPE_SMALLINT,
    "INT2": LOCAL_TYPE_SMALLINT,
    "SMALLSERIAL": LOCAL_TYPE_SMALLINT,
    "INTEGER": LOCAL_TYPE_INT,
    "INT": LOCAL_TYPE_INT,
    "INT4": LOCAL_TYPE_INT,
    "SERIAL": LOCAL_TYPE_INT,
    "BIGSERIAL": LOCAL_TYPE_BIGINT,
    "REAL": LOCAL_TYPE_REAL,
    "FLOAT4": LOCAL_TYPE_REAL,
    "TEXT": LOCAL_TYPE_TEXT,
    "UUID": "UUID",
    "INET": "INET",
    "INTERVAL": "INTERVAL",
    "TIMESTAMPTZ": LOCAL_TYPE_TIMESTAMPTZ,
    "TIMESTAMP WITH TIME ZONE": LOCAL_TYPE_TIMESTAMPTZ,
}
_POSTGRES_ARRAY_ELEMENT_LOCAL_TYPES: dict[str, str] = {
    "SMALLINT": LOCAL_TYPE_SMALLINT,
    "INT2": LOCAL_TYPE_SMALLINT,
    "INTEGER": LOCAL_TYPE_INT,
    "INT": LOCAL_TYPE_INT,
    "INT4": LOCAL_TYPE_INT,
    "BIGINT": LOCAL_TYPE_BIGINT,
    "INT8": LOCAL_TYPE_BIGINT,
    "TEXT": LOCAL_TYPE_TEXT,
    "VARCHAR": LOCAL_TYPE_VARCHAR,
    "BOOLEAN": LOCAL_TYPE_BOOLEAN,
    "BOOL": LOCAL_TYPE_BOOLEAN,
    "REAL": LOCAL_TYPE_REAL,
    "FLOAT4": LOCAL_TYPE_REAL,
    "DOUBLE PRECISION": LOCAL_TYPE_DOUBLE,
    "FLOAT8": LOCAL_TYPE_DOUBLE,
    "NUMERIC": LOCAL_TYPE_DECIMAL,
    "DECIMAL": LOCAL_TYPE_DECIMAL,
    "UUID": "UUID",
}


def build_scenario_snapshot_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation_name: str,
    local_type_overrides: dict[str, str] | None = None,
) -> tuple[ScenarioSnapshotColumn, ...]:
    """Return local snapshot column metadata for a materialized relation."""

    column_infos: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection=connection,
        relation=relation_name,
    )
    return tuple(
        ScenarioSnapshotColumn(
            name=column.name,
            warehouse_type=column.type,
            local_type=local_type_for_warehouse_type(
                warehouse_type=column.type,
                sql_analysis_dialect=adapter.sql_analysis_dialect(),
                local_type_overrides=local_type_overrides,
            ),
        )
        for column in column_infos
    )


def local_type_for_warehouse_type(
    *,
    warehouse_type: str,
    sql_analysis_dialect: str | None = None,
    local_type_overrides: dict[str, str] | None = None,
) -> str:
    """Map a warehouse type string to a DuckDB-compatible local replay type."""

    override_type: str | None = _local_type_from_overrides(
        warehouse_type=warehouse_type,
        local_type_overrides=local_type_overrides or {},
    )
    if override_type is not None:
        return override_type

    dialect: TypeDialect | None = _coerce_type_dialect(sql_analysis_dialect)
    if dialect == TypeDialect.POSTGRES:
        postgres_type: str | None = _postgres_pre_local_type(warehouse_type)
        if postgres_type is not None:
            return postgres_type

    dialect_type: str | None = _dialect_pre_local_type(
        warehouse_type=warehouse_type,
        sql_analysis_dialect=sql_analysis_dialect,
    )
    if dialect_type is not None:
        return dialect_type

    polyglot_local_type: str | None = _local_type_with_polyglot(
        warehouse_type=warehouse_type,
        sql_analysis_dialect=sql_analysis_dialect,
    )
    if polyglot_local_type is not None:
        return polyglot_local_type

    return _fallback_local_type_for_warehouse_type(warehouse_type)


def _local_type_from_overrides(
    *, warehouse_type: str, local_type_overrides: dict[str, str]
) -> str | None:
    if not local_type_overrides:
        return None
    warehouse_pattern: _TypePattern = _parse_type_pattern(warehouse_type)
    matches: list[tuple[int, str]] = []
    pattern: str
    local_type_template: str
    for pattern, local_type_template in local_type_overrides.items():
        override_pattern: _TypePattern = _parse_type_pattern(pattern)
        specificity: int | None = _type_pattern_specificity(
            pattern=override_pattern,
            warehouse_type=warehouse_pattern,
        )
        if specificity is None:
            continue
        matches.append(
            (
                specificity,
                _render_local_type_template(
                    template=local_type_template,
                    args=warehouse_pattern.args,
                ),
            )
        )
    if not matches:
        return None
    best_specificity: int = max(specificity for specificity, _local_type in matches)
    best_local_types: set[str] = {
        local_type for specificity, local_type in matches if specificity == best_specificity
    }
    if len(best_local_types) > 1:
        raise ExecutorInputError(
            "Multiple local type override patterns match "
            f"'{warehouse_type}' with equal specificity",
            code=SCENARIO_LOCAL_TYPE_INVALID,
            help=(
                "Make one scenario local type override pattern more specific or remove the "
                "duplicate."
            ),
        )
    return best_local_types.pop()


def _postgres_pre_local_type(warehouse_type: str) -> str | None:
    pattern: _TypePattern = _parse_type_pattern(warehouse_type)
    base: str = pattern.base
    args: tuple[str, ...] = pattern.args
    if base in _POSTGRES_DIRECT_LOCAL_TYPES:
        return _POSTGRES_DIRECT_LOCAL_TYPES[base]
    if base in POSTGRES_PARAMETERIZED_TEXT_TYPES and args:
        return f"TEXT({args[0]})"
    if base in POSTGRES_PARAMETERIZED_DECIMAL_TYPES and args:
        return "DECIMAL(" + ", ".join(args) + ")"
    if base.endswith("[]"):
        element_base: str = base[:-2].strip()
        mapped: str | None = _POSTGRES_ARRAY_ELEMENT_LOCAL_TYPES.get(element_base)
        if mapped is not None:
            return f"{mapped}[]"
    return None


def _dialect_pre_local_type(*, warehouse_type: str, sql_analysis_dialect: str | None) -> str | None:
    pattern: _TypePattern = _parse_type_pattern(warehouse_type)
    base: str = pattern.base
    args: tuple[str, ...] = pattern.args
    dialect: TypeDialect | None = _coerce_type_dialect(sql_analysis_dialect)
    if dialect == TypeDialect.SNOWFLAKE:
        return _snowflake_pre_local_type(base=base, args=args)
    if dialect == TypeDialect.BIGQUERY:
        return _bigquery_pre_local_type(base=base, args=args)
    if dialect == TypeDialect.DATABRICKS:
        return _databricks_pre_local_type(base=base, args=args)
    if dialect == TypeDialect.DUCKDB:
        return _duckdb_pre_local_type(base=base, args=args)
    if dialect is None and base not in FALLBACK_POLYGLOT_BASE_TYPES:
        return LOCAL_TYPE_VARCHAR
    return None


def _snowflake_pre_local_type(*, base: str, args: tuple[str, ...]) -> str | None:
    if base == SNOWFLAKE_NUMBER_TYPE:
        precision_and_scale_count: int = 2
        if len(args) >= precision_and_scale_count:
            return f"DECIMAL({args[0]}, {args[1]})"
        if len(args) == 1:
            return f"DECIMAL({args[0]})"
        return "DECIMAL(38, 0)"
    if base in SNOWFLAKE_DOUBLE_TYPES:
        return LOCAL_TYPE_DOUBLE
    if base == SNOWFLAKE_REAL_TYPE:
        return LOCAL_TYPE_REAL
    if base in SNOWFLAKE_TIMEZONE_TIMESTAMP_TYPES:
        return LOCAL_TYPE_TIMESTAMPTZ
    if base == SNOWFLAKE_TIMESTAMP_NTZ_TYPE:
        return f"TIMESTAMP({args[0]})" if args else LOCAL_TYPE_TIMESTAMP
    return None


def _bigquery_pre_local_type(*, base: str, args: tuple[str, ...]) -> str | None:
    if base == BIGQUERY_BIGNUMERIC_TYPE:
        precision_and_scale_count: int = 2
        if len(args) >= precision_and_scale_count:
            return f"DECIMAL({args[0]}, {args[1]})"
        return "DECIMAL(38, 5)"
    if base in BIGQUERY_VARCHAR_TYPES:
        return LOCAL_TYPE_VARCHAR
    if base == BIGQUERY_TIMESTAMP_TYPE:
        return LOCAL_TYPE_TIMESTAMPTZ
    return None


def _databricks_pre_local_type(*, base: str, args: tuple[str, ...]) -> str | None:
    if base == DATABRICKS_TIMESTAMP_TYPE:
        return LOCAL_TYPE_TIMESTAMPTZ
    if base == DATABRICKS_TIMESTAMP_NTZ_TYPE:
        return LOCAL_TYPE_TIMESTAMP
    if base == DATABRICKS_VOID_TYPE:
        return LOCAL_TYPE_VARCHAR
    return None


def _duckdb_pre_local_type(*, base: str, args: tuple[str, ...]) -> str | None:
    if base == DUCKDB_HUGEINT_TYPE:
        return LOCAL_TYPE_INT128
    if base == DUCKDB_UHUGEINT_TYPE:
        return LOCAL_TYPE_UINT128
    if base == DUCKDB_BLOB_TYPE:
        return LOCAL_TYPE_VARCHAR
    if base == DUCKDB_LIST_TYPE and args:
        inner_type: str = _fallback_local_type_for_warehouse_type(args[0])
        if inner_type == LOCAL_TYPE_BIGINT and args[0].strip().upper() == DUCKDB_INTEGER_TYPE:
            inner_type = LOCAL_TYPE_INT
        return inner_type + "[]"
    return None


def _local_type_with_polyglot(
    *, warehouse_type: str, sql_analysis_dialect: str | None
) -> str | None:
    polyglot_module: Any | None = import_polyglot()
    if polyglot_module is None:
        return None

    try:
        data_type: Any = polyglot_module.parse_data_type(
            warehouse_type,
            dialect=sql_analysis_dialect or "generic",
        )
    except Exception as error:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="scenario snapshot type polyglot conversion failed; falling back",
            warehouse_type=warehouse_type,
            sql_analysis_dialect=sql_analysis_dialect,
            sqlbuild_error=str(error),
        )
        return None

    type_name: str = _polyglot_type_name(data_type)
    base_type: str = _parse_type_pattern(warehouse_type).base
    if type_name in POLYGLOT_DECIMAL_TYPES:
        rendered_bigdecimal_type: str = data_type.sql(dialect="duckdb").strip()
        if MALFORMED_RENDERED_TYPE_TOKEN not in rendered_bigdecimal_type:
            return rendered_bigdecimal_type
        return _decimal_local_type_from_polyglot(data_type) or LOCAL_TYPE_VARCHAR
    if type_name in POLYGLOT_VARCHAR_TYPES:
        return LOCAL_TYPE_VARCHAR
    if type_name == POLYGLOT_OBJECT_TYPE:
        return LOCAL_TYPE_JSON
    if type_name == POLYGLOT_ARRAY_TYPE and not _polyglot_element_type(data_type):
        return LOCAL_TYPE_JSON
    if type_name in POLYGLOT_COLLECTION_TYPES and _polyglot_element_type(data_type):
        return data_type.sql(dialect="duckdb").strip()
    if type_name in POLYGLOT_SPATIAL_AND_MONEY_TYPES:
        return LOCAL_TYPE_VARCHAR
    dialect: TypeDialect | None = _coerce_type_dialect(sql_analysis_dialect)
    if dialect == TypeDialect.POSTGRES and base_type in POSTGRES_VARCHAR_TYPES:
        return LOCAL_TYPE_VARCHAR
    if dialect == TypeDialect.POSTGRES and base_type in POSTGRES_SERIAL_TYPES:
        return _postgres_serial_local_type(base_type)
    if (
        dialect == TypeDialect.BIGQUERY
        and base_type == BIGQUERY_BYTES_TYPE
        and data_type.expressions
    ):
        return LOCAL_TYPE_VARCHAR
    if dialect == TypeDialect.SNOWFLAKE and base_type == SNOWFLAKE_VECTOR_TYPE:
        return LOCAL_TYPE_JSON

    local_type: str = data_type.sql(dialect="duckdb").strip()
    if (
        not local_type
        or local_type == UNTYPED_ARRAY_TYPE
        or MALFORMED_RENDERED_TYPE_TOKEN in local_type
    ):
        return _fallback_local_type_for_warehouse_type(warehouse_type)
    if local_type.startswith("BLOB"):
        return "VARCHAR"
    if local_type.startswith("TIMESTAMPTZ("):
        return "TIMESTAMPTZ"
    if local_type == LOCAL_TYPE_REAL and _should_widen_real_to_double(
        warehouse_type=warehouse_type,
        sql_analysis_dialect=sql_analysis_dialect,
    ):
        return LOCAL_TYPE_DOUBLE
    return local_type


def _fallback_local_type_for_warehouse_type(warehouse_type: str) -> str:
    """Return a conservative local type when SQL analysis cannot classify a type."""

    normalized_type: str = warehouse_type.strip().upper()
    base_type: str = normalized_type.split("(", 1)[0].strip()
    if base_type in FALLBACK_BOOLEAN_TYPES:
        return LOCAL_TYPE_BOOLEAN
    if base_type in FALLBACK_SIGNED_INTEGER_TYPES:
        return LOCAL_TYPE_BIGINT
    if base_type in FALLBACK_UNSIGNED_INTEGER_TYPES:
        return LOCAL_TYPE_BIGINT
    if base_type in FALLBACK_FLOAT_TYPES:
        return LOCAL_TYPE_DOUBLE
    if base_type in FALLBACK_DECIMAL_TYPES:
        return _decimal_local_type(normalized_type)
    if base_type == FALLBACK_DATE_TYPE:
        return LOCAL_TYPE_DATE
    if base_type in FALLBACK_TIME_TYPES:
        return LOCAL_TYPE_TIME
    if FALLBACK_TIMESTAMP_TOKEN in base_type or base_type in FALLBACK_TIMESTAMP_TYPES:
        return LOCAL_TYPE_TIMESTAMP
    if base_type in FALLBACK_VARCHAR_TYPES:
        return LOCAL_TYPE_VARCHAR
    if base_type in FALLBACK_JSON_TYPES:
        return LOCAL_TYPE_JSON
    if base_type in FALLBACK_BINARY_TYPES:
        return LOCAL_TYPE_VARCHAR
    if base_type in FALLBACK_STRUCTURED_TYPES:
        return LOCAL_TYPE_JSON
    return LOCAL_TYPE_VARCHAR


def _postgres_serial_local_type(base_type: str) -> str:
    if base_type == POSTGRES_BIGSERIAL_TYPE:
        return LOCAL_TYPE_BIGINT
    if base_type == POSTGRES_SMALLSERIAL_TYPE:
        return LOCAL_TYPE_SMALLINT
    return LOCAL_TYPE_INT


def _parse_type_pattern(type_text: str) -> _TypePattern:
    normalized_type: str = type_text.strip().upper()
    if not normalized_type:
        return _TypePattern(base="")
    open_index: int = _first_type_arg_open_index(normalized_type)
    if open_index == -1:
        return _TypePattern(base=normalized_type)
    close_char: str = (
        TYPE_ARGUMENT_CLOSE_PAREN
        if normalized_type[open_index] == TYPE_ARGUMENT_OPEN_PAREN
        else TYPE_ARGUMENT_CLOSE_ANGLE
    )
    close_index: int = normalized_type.rfind(close_char)
    if close_index == -1 or close_index < open_index:
        return _TypePattern(base=normalized_type)
    base: str = normalized_type[:open_index].strip()
    args_text: str = normalized_type[open_index + 1 : close_index].strip()
    return _TypePattern(base=base, args=tuple(_split_type_args(args_text)))


def _first_type_arg_open_index(type_text: str) -> int:
    paren_index: int = type_text.find("(")
    angle_index: int = type_text.find("<")
    indexes: tuple[int, ...] = tuple(index for index in (paren_index, angle_index) if index != -1)
    if not indexes:
        return -1
    return min(indexes)


def _split_type_args(args_text: str) -> list[str]:
    if not args_text:
        return []
    args: list[str] = []
    start: int = 0
    depth: int = 0
    index: int
    character: str
    for index, character in enumerate(args_text):
        if character in TYPE_ARGUMENT_OPEN_TOKENS:
            depth += 1
        elif character in TYPE_ARGUMENT_CLOSE_TOKENS:
            depth = max(depth - 1, 0)
        elif character == TYPE_ARGUMENT_SEPARATOR and depth == 0:
            args.append(args_text[start:index].strip())
            start = index + 1
    args.append(args_text[start:].strip())
    return args


def _type_pattern_specificity(*, pattern: _TypePattern, warehouse_type: _TypePattern) -> int | None:
    if pattern.base != TYPE_PATTERN_WILDCARD and pattern.base != warehouse_type.base:
        return None
    if len(pattern.args) != len(warehouse_type.args):
        return None
    specificity: int = 0 if pattern.base == TYPE_PATTERN_WILDCARD else 100
    pattern_arg: str
    warehouse_arg: str
    for pattern_arg, warehouse_arg in zip(pattern.args, warehouse_type.args, strict=True):
        if pattern_arg == TYPE_PATTERN_WILDCARD:
            continue
        if pattern_arg != warehouse_arg:
            return None
        specificity += 10
    return specificity


def _render_local_type_template(*, template: str, args: tuple[str, ...]) -> str:
    rendered: str = template
    index: int
    arg: str
    for index, arg in enumerate(args, start=1):
        rendered = rendered.replace(f"{{{index}}}", arg)
    return rendered


def _decimal_local_type(normalized_type: str) -> str:
    """Return a DuckDB decimal type preserving precision and scale when present."""

    if TYPE_ARGUMENT_OPEN_PAREN not in normalized_type:
        return LOCAL_TYPE_DECIMAL
    precision_scale: str = normalized_type.split("(", 1)[1].split(")", 1)[0].strip()
    if not precision_scale:
        return LOCAL_TYPE_DECIMAL
    return f"DECIMAL({precision_scale})"


def _decimal_local_type_from_polyglot(data_type: Any) -> str | None:
    precision_scale: str | None = _polyglot_precision_scale(data_type)
    if precision_scale is None:
        return LOCAL_TYPE_DECIMAL
    return f"DECIMAL({precision_scale})"


def _polyglot_precision_scale(data_type: Any) -> str | None:
    args: dict[str, Any] = dict(getattr(data_type, "args", {}) or {})
    values: list[str] = [
        str(value) for value in (args.get("precision"), args.get("scale")) if value is not None
    ]
    if not values:
        return None
    return ", ".join(values)


def _polyglot_type_name(data_type: Any) -> str:
    args: dict[str, Any] = dict(getattr(data_type, "args", {}) or {})
    data_type_name: str = str(args.get("data_type", "")).upper()
    if data_type_name == POLYGLOT_CUSTOM_TYPE:
        return str(args.get("name", "")).upper().replace(" ", "")
    return data_type_name


def _polyglot_element_type(data_type: Any) -> dict[str, Any] | None:
    args: dict[str, Any] = dict(getattr(data_type, "args", {}) or {})
    element_type: Any = args.get("element_type")
    return element_type if isinstance(element_type, dict) else None


def _should_widen_real_to_double(*, warehouse_type: str, sql_analysis_dialect: str | None) -> bool:
    normalized_type: str = warehouse_type.strip().upper()
    base_type: str = normalized_type.split("(", 1)[0].strip()
    dialect: TypeDialect | None = _coerce_type_dialect(sql_analysis_dialect)
    if dialect == TypeDialect.SNOWFLAKE:
        return base_type in SNOWFLAKE_WIDEN_TO_DOUBLE_TYPES
    if dialect == TypeDialect.BIGQUERY:
        return base_type in BIGQUERY_WIDEN_TO_DOUBLE_TYPES
    return base_type in GENERIC_WIDEN_TO_DOUBLE_TYPES


def _coerce_type_dialect(dialect: str | None) -> TypeDialect | None:
    if dialect is None:
        return None
    try:
        return TypeDialect(dialect)
    except ValueError:
        return None
