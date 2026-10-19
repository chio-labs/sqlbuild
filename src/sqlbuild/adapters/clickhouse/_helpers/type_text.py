"""ClickHouse type text helpers shared by inspection, diff and contracts."""

from __future__ import annotations

from sqlbuild.adapters.clickhouse.constants import (
    DECIMAL_ALIAS,
    DECIMAL_BASE_TYPE,
    DECIMAL_PRECISION_BY_BASE,
    LOW_CARDINALITY_WRAPPER,
    NULLABLE_WRAPPER,
    TYPE_ALIASES,
    TYPE_WRAPPERS,
    UNWRAPPABLE_TYPE_BASES,
)


def quote_string(value: str) -> str:
    """Quote one string literal; ClickHouse treats backslash as an escape character."""

    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def strip_type_wrappers(type_sql: str) -> str:
    """Remove the ``Nullable`` and ``LowCardinality`` wrappers that do not change values."""

    stripped: str = type_sql.strip()
    changed: bool = True
    while changed:
        changed = False
        wrapper: str
        for wrapper in TYPE_WRAPPERS:
            inner: str | None = _unwrap(type_sql=stripped, wrapper=wrapper)
            if inner is not None:
                stripped = inner
                changed = True
    return stripped


def is_nullable_type(type_sql: str) -> bool:
    """Return whether a ClickHouse column type admits NULL."""

    stripped: str = type_sql.strip()
    low_cardinality_inner: str | None = _unwrap(type_sql=stripped, wrapper=LOW_CARDINALITY_WRAPPER)
    if low_cardinality_inner is not None:
        stripped = low_cardinality_inner
    return _unwrap(type_sql=stripped, wrapper=NULLABLE_WRAPPER) is not None


def canonical_type(type_sql: str) -> str:
    """Map one ClickHouse type to the portable spelling the shared type system compares."""

    stripped: str = strip_type_wrappers(type_sql)
    base: str = _base_type(stripped)
    params: str = stripped[len(base) :].strip()
    alias: str | None = TYPE_ALIASES.get(base)
    if alias is None:
        return stripped
    if alias == DECIMAL_ALIAS and params:
        inner: list[str] = [part.strip() for part in params[1:-1].split(",")]
        if base == DECIMAL_BASE_TYPE:
            return f"{DECIMAL_ALIAS}({', '.join(inner)})"
        return f"{DECIMAL_ALIAS}({DECIMAL_PRECISION_BY_BASE[base]}, {inner[0]})"
    return alias


def nullable_type(type_sql: str) -> str:
    """Wrap a scalar type in ``Nullable`` unless it already admits NULL or cannot be wrapped."""

    stripped: str = type_sql.strip()
    if is_nullable_type(stripped):
        return stripped
    if _base_type(stripped) in UNWRAPPABLE_TYPE_BASES:
        return stripped
    low_cardinality_inner: str | None = _unwrap(type_sql=stripped, wrapper=LOW_CARDINALITY_WRAPPER)
    if low_cardinality_inner is not None:
        return f"{LOW_CARDINALITY_WRAPPER}({NULLABLE_WRAPPER}({low_cardinality_inner}))"
    return f"{NULLABLE_WRAPPER}({stripped})"


def _base_type(type_sql: str) -> str:
    return type_sql.split("(", 1)[0].strip()


def _unwrap(*, type_sql: str, wrapper: str) -> str | None:
    prefix: str = f"{wrapper}("
    if type_sql.startswith(prefix) and type_sql.endswith(")"):
        return type_sql[len(prefix) : -1].strip()
    return None
