"""Table creation that keeps declared column types, which SQLite's CTAS discards."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlbuild.adapters.sqlite._helpers.catalog import quote_identifier
from sqlbuild.adapters.sqlite.constants import DECIMAL_TEXT_TYPE_PREFIX, EXACT_DECIMAL_TYPE_PATTERN

_CREATE_TABLE_AS: re.Pattern[str] = re.compile(
    r"^\s*CREATE\s+TABLE\s+(?!IF\s)(?!TEMP\s)(?!TEMPORARY\s)"
    r"(\"(?:[^\"]|\"\")+\"|[^\s(]+)\s+AS\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_UNTYPED_VIEW_COLUMN_TYPE: str = "BLOB"
_DECIMAL_TYPE: re.Pattern[str] = re.compile(EXACT_DECIMAL_TYPE_PATTERN, re.IGNORECASE)


def split_create_table_as(sql: str) -> tuple[str, str] | None:
    """Return (destination, select) when one statement is a plain CREATE TABLE AS."""

    match: re.Match[str] | None = _CREATE_TABLE_AS.match(sql)
    if match is None:
        return None
    return match.group(1), match.group(2)


def create_table_typed(
    *,
    connection: Any,
    destination: str,
    sql: str,
    column_types: Mapping[str, str],
    inferred_types: Mapping[str, str],
) -> Any:
    """Create `destination` with passed-through, inferred or enforced types, atomically."""

    probe: str = f"_sqlbuild_probe_{uuid4().hex}"
    owns_transaction: bool = not connection.in_transaction()
    connection.execute("BEGIN IMMEDIATE" if owns_transaction else f"SAVEPOINT {probe}")
    try:
        connection.execute(f"CREATE TEMP VIEW {probe} AS {sql}")
        rows: list[tuple[Any, ...]] = connection.execute(
            f"PRAGMA temp.table_xinfo({probe})"
        ).fetchall()
        connection.execute(f"DROP VIEW temp.{probe}")
        column_sql: str = ", ".join(
            _column_definition(
                name=str(row[1]),
                declared=_probed_type(row[2]) or inferred_types.get(str(row[1]).lower(), ""),
                column_types=column_types,
            )
            for row in rows
        )
        connection.execute(f"CREATE TABLE {destination} ({column_sql})")
        cursor: Any = connection.execute(f"INSERT INTO {destination} SELECT * FROM ({sql})")
    except BaseException:
        if connection.in_transaction():
            connection.execute("ROLLBACK" if owns_transaction else f"ROLLBACK TO {probe}")
            if not owns_transaction:
                connection.execute(f"RELEASE {probe}")
        raise
    connection.execute("COMMIT" if owns_transaction else f"RELEASE {probe}")
    return cursor


def storage_type(declared: str) -> str:
    """Return the type a column is declared with; `DECIMAL(p,s)` is stored as canonical text."""

    if _DECIMAL_TYPE.match(declared) is None:
        return declared
    return f"{DECIMAL_TEXT_TYPE_PREFIX}{declared.strip()}"


def decimal_scale(target_type: str) -> int | None:
    """Return a `DECIMAL(p,s)` type's scale, or None for any other type, including bare DECIMAL."""

    match: re.Match[str] | None = _DECIMAL_TYPE.match(target_type)
    if match is None:
        return None
    return int(match.group(2) or 0)


def _probed_type(declared: object) -> str:
    """A view reports an untyped source column as BLOB; keep such columns untyped."""

    text: str = str(declared or "")
    return "" if text.upper() == _UNTYPED_VIEW_COLUMN_TYPE else text


def _column_definition(*, name: str, declared: str, column_types: Mapping[str, str]) -> str:
    override: str | None = column_types.get(name.lower())
    column_type: str = storage_type(override) if override is not None else declared
    return f"{quote_identifier(name)} {column_type}".rstrip()
