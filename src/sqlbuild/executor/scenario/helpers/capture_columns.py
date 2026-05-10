"""Scenario snapshot column metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.executor.scenario.models import ScenarioSnapshotColumn
from sqlbuild.shared.helpers.sqlglot import import_sqlglot_expressions


@dataclass(frozen=True)
class _TypePattern:
    base: str
    args: tuple[str, ...] = ()


_POSTGRES_SERIAL_TYPES: frozenset[str] = frozenset({"BIGSERIAL", "SERIAL", "SMALLSERIAL"})
_POSTGRES_VARCHAR_TYPES: frozenset[str] = frozenset(
    {
        "CIDR",
        "CIRCLE",
        "DATERANGE",
        "INT4RANGE",
        "INT8RANGE",
        "LINE",
        "LSEG",
        "MACADDR",
        "MACADDR8",
        "NAME",
        "NUMRANGE",
        "PATH",
        "POINT",
        "POLYGON",
        "REGCLASS",
        "TSQUERY",
        "TSRANGE",
        "TSTZRANGE",
        "TSVECTOR",
        "VARBIT",
    }
)


def build_scenario_snapshot_columns(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relation_name: str,
    local_type_overrides: dict[str, str] | None = None,
) -> tuple[ScenarioSnapshotColumn, ...]:
    """Return local snapshot column metadata for a materialized relation."""

    column_infos: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection,
        relation_name,
    )
    return tuple(
        ScenarioSnapshotColumn(
            name=column.name,
            warehouse_type=column.type,
            local_type=local_type_for_warehouse_type(
                column.type,
                sqlglot_dialect=adapter.sqlglot_dialect(),
                local_type_overrides=local_type_overrides,
            ),
        )
        for column in column_infos
    )


def local_type_for_warehouse_type(
    warehouse_type: str,
    *,
    sqlglot_dialect: str | None = None,
    local_type_overrides: dict[str, str] | None = None,
) -> str:
    """Map a warehouse type string to a DuckDB-compatible local replay type."""

    override_type: str | None = _local_type_from_overrides(
        warehouse_type=warehouse_type,
        local_type_overrides=local_type_overrides or {},
    )
    if override_type is not None:
        return override_type

    sqlglot_local_type: str | None = _local_type_with_sqlglot(
        warehouse_type=warehouse_type,
        sqlglot_dialect=sqlglot_dialect,
    )
    if sqlglot_local_type is not None:
        return sqlglot_local_type

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
        raise ValueError(
            f"Multiple local type override patterns match '{warehouse_type}' with equal specificity"
        )
    return best_local_types.pop()


def _local_type_with_sqlglot(*, warehouse_type: str, sqlglot_dialect: str | None) -> str | None:
    expressions_module: Any | None = import_sqlglot_expressions()
    if expressions_module is None:
        return None

    try:
        data_type: Any = expressions_module.DataType.build(
            warehouse_type,
            dialect=sqlglot_dialect,
        )
    except Exception:
        return None

    type_name: str = _sqlglot_type_name(data_type)
    base_type: str = _parse_type_pattern(warehouse_type).base
    if type_name == "BIGDECIMAL":
        rendered_bigdecimal_type: str = data_type.sql(dialect="duckdb").strip()
        if ")(" not in rendered_bigdecimal_type:
            return rendered_bigdecimal_type
        return _decimal_local_type_from_sqlglot(data_type) or "VARCHAR"
    if type_name in {"NULL", "RANGE", "XML"}:
        return "VARCHAR"
    if type_name == "OBJECT":
        return "JSON"
    if type_name == "ARRAY" and not data_type.expressions:
        return "JSON"
    if type_name == "LIST" and data_type.expressions:
        return data_type.expressions[0].sql(dialect="duckdb").strip() + "[]"
    if type_name in {"GEOGRAPHY", "GEOMETRY", "MONEY"}:
        return "VARCHAR"
    if sqlglot_dialect == "postgres" and base_type in _POSTGRES_VARCHAR_TYPES:
        return "VARCHAR"
    if sqlglot_dialect == "postgres" and base_type in _POSTGRES_SERIAL_TYPES:
        return _postgres_serial_local_type(base_type)
    if sqlglot_dialect == "bigquery" and base_type == "BYTES" and data_type.expressions:
        return "VARCHAR"
    if sqlglot_dialect == "snowflake" and base_type == "VECTOR":
        return "JSON"

    local_type: str = data_type.sql(dialect="duckdb").strip()
    if not local_type or local_type == "[]" or ")(" in local_type:
        return _fallback_local_type_for_warehouse_type(warehouse_type)
    if local_type.startswith("BLOB"):
        return "VARCHAR"
    if local_type.startswith("TIMESTAMPTZ("):
        return "TIMESTAMPTZ"
    if local_type == "REAL" and _should_widen_real_to_double(
        warehouse_type=warehouse_type,
        sqlglot_dialect=sqlglot_dialect,
    ):
        return "DOUBLE"
    return local_type


def _fallback_local_type_for_warehouse_type(warehouse_type: str) -> str:
    """Return a conservative local type when SQLGlot cannot classify a type."""

    normalized_type: str = warehouse_type.strip().upper()
    base_type: str = normalized_type.split("(", 1)[0].strip()
    if base_type in {"BOOL", "BOOLEAN"}:
        return "BOOLEAN"
    if base_type in {"TINYINT", "SMALLINT", "INT", "INTEGER", "BIGINT", "HUGEINT"}:
        return "BIGINT"
    if base_type in {"UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT"}:
        return "BIGINT"
    if base_type in {"FLOAT", "FLOAT4", "REAL", "DOUBLE", "DOUBLE PRECISION", "FLOAT8"}:
        return "DOUBLE"
    if base_type in {"DECIMAL", "DEC", "NUMERIC", "NUMBER"}:
        return _decimal_local_type(normalized_type)
    if base_type == "DATE":
        return "DATE"
    if base_type in {"TIME", "TIME WITH TIME ZONE", "TIMETZ"}:
        return "TIME"
    if "TIMESTAMP" in base_type or base_type in {"DATETIME", "TIMESTAMPTZ"}:
        return "TIMESTAMP"
    if base_type in {"VARCHAR", "CHAR", "CHARACTER", "TEXT", "STRING"}:
        return "VARCHAR"
    if base_type in {"JSON", "JSONB"}:
        return "JSON"
    if base_type in {"BLOB", "BYTEA", "BINARY", "VARBINARY"}:
        return "VARCHAR"
    if base_type in {"ARRAY", "OBJECT", "VARIANT", "JSON", "JSONB"}:
        return "JSON"
    return "VARCHAR"


def _postgres_serial_local_type(base_type: str) -> str:
    if base_type == "BIGSERIAL":
        return "BIGINT"
    if base_type == "SMALLSERIAL":
        return "SMALLINT"
    return "INT"


def _parse_type_pattern(type_text: str) -> _TypePattern:
    normalized_type: str = type_text.strip().upper()
    if not normalized_type:
        return _TypePattern(base="")
    open_index: int = _first_type_arg_open_index(normalized_type)
    if open_index == -1:
        return _TypePattern(base=normalized_type)
    close_char: str = ")" if normalized_type[open_index] == "(" else ">"
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
        if character in "(<":
            depth += 1
        elif character in ")>":
            depth = max(depth - 1, 0)
        elif character == "," and depth == 0:
            args.append(args_text[start:index].strip())
            start = index + 1
    args.append(args_text[start:].strip())
    return args


def _type_pattern_specificity(*, pattern: _TypePattern, warehouse_type: _TypePattern) -> int | None:
    if pattern.base != "*" and pattern.base != warehouse_type.base:
        return None
    if len(pattern.args) != len(warehouse_type.args):
        return None
    specificity: int = 0 if pattern.base == "*" else 100
    pattern_arg: str
    warehouse_arg: str
    for pattern_arg, warehouse_arg in zip(pattern.args, warehouse_type.args, strict=True):
        if pattern_arg == "*":
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

    if "(" not in normalized_type:
        return "DECIMAL"
    precision_scale: str = normalized_type.split("(", 1)[1].split(")", 1)[0].strip()
    if not precision_scale:
        return "DECIMAL"
    return f"DECIMAL({precision_scale})"


def _decimal_local_type_from_sqlglot(data_type: Any) -> str | None:
    precision_scale: str | None = _sqlglot_precision_scale(data_type)
    if precision_scale is None:
        return "DECIMAL"
    return f"DECIMAL({precision_scale})"


def _sqlglot_precision_scale(data_type: Any) -> str | None:
    values: list[str] = []
    expression: Any
    for expression in data_type.expressions:
        value: Any = getattr(expression, "this", None)
        text: str = getattr(value, "this", "")
        if text == "":
            return None
        values.append(str(text))
    if not values:
        return None
    return ", ".join(values)


def _sqlglot_type_name(data_type: Any) -> str:
    data_type_kind: Any = getattr(data_type, "this", None)
    return str(getattr(data_type_kind, "name", "")).upper()


def _should_widen_real_to_double(*, warehouse_type: str, sqlglot_dialect: str | None) -> bool:
    normalized_type: str = warehouse_type.strip().upper()
    base_type: str = normalized_type.split("(", 1)[0].strip()
    if sqlglot_dialect == "snowflake":
        return base_type in {"FLOAT", "FLOAT8", "DOUBLE", "DOUBLE PRECISION"}
    if sqlglot_dialect == "bigquery":
        return base_type in {"FLOAT64"}
    return base_type in {"DOUBLE", "DOUBLE PRECISION", "FLOAT8"}
