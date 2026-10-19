"""SQLite catalog reads: one file holds every schema as `schema__name` relations."""

from __future__ import annotations

import re
from typing import Any

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.sqlite.constants import (
    BASE_TABLE_RELATION_TYPE,
    DECIMAL_TEXT_TYPE_PREFIX,
    DECIMAL_TYPE_NAMES,
    IDENTIFIER_QUOTE,
    INVALID_SCHEMA_NAME_CODE,
    MAIN_SCHEMA,
    MAIN_SCHEMA_PREFIX,
    SCHEMA_NAME_SEPARATOR,
    SCHEMA_REGISTRY_TABLE,
    SQLITE_INTERNAL_PREFIX,
    SQLITE_VIEW_TYPE,
    TYPEOF_TYPE_NAMES,
    UNTYPED_COLUMN_TYPE,
    VIEW_BODY_PATTERN,
    VIEW_RELATION_TYPE,
)

_VIEW_BODY: re.Pattern[str] = re.compile(VIEW_BODY_PATTERN, re.IGNORECASE | re.DOTALL)


def validate_schema_name(schema: str) -> None:
    """Reject schema names that would make `schema__name` relations ambiguous."""

    if SCHEMA_NAME_SEPARATOR in schema or schema.endswith("_") or not schema:
        raise AdapterUserError(
            message=(
                f"SQLite schema '{schema}' cannot contain '{SCHEMA_NAME_SEPARATOR}' or end with "
                "'_', because SQLite stores schema relations as '<schema>__<name>'"
            ),
            code=INVALID_SCHEMA_NAME_CODE,
        )


def physical_name(*, schema: str | None, name: str) -> str:
    """Return the table name one logical relation is stored under."""

    if schema is None or schema.lower() == MAIN_SCHEMA:
        return name
    validate_schema_name(schema)
    return f"{schema}{SCHEMA_NAME_SEPARATOR}{name}"


def unquote_relation(relation: str) -> str:
    """Return the physical table name from a rendered relation reference."""

    text: str = relation.strip()
    if text.lower().startswith(MAIN_SCHEMA_PREFIX):
        text = text[len(MAIN_SCHEMA_PREFIX) :]
    quoted_length: int = 2
    if len(text) >= quoted_length and text[0] == text[-1] == IDENTIFIER_QUOTE:
        return text[1:-1].replace('""', '"')
    return text


def registered_schemas(connection: Any) -> frozenset[str]:
    """Return schemas SQLBuild created, which decide how `a__b` names split."""

    exists: object = connection.execute_with(
        sql="SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?",
        parameters=(SCHEMA_REGISTRY_TABLE,),
    ).fetchone()
    if exists is None:
        return frozenset()
    rows: list[tuple[Any, ...]] = connection.execute(
        f"SELECT schema_name FROM {SCHEMA_REGISTRY_TABLE}"
    ).fetchall()
    return frozenset(str(row[0]).lower() for row in rows)


def logical_location(*, table_name: str, schemas: frozenset[str]) -> tuple[str, str]:
    """Split one physical table name into its schema and relation name."""

    prefix: str
    rest: str
    prefix, separator, rest = table_name.partition(SCHEMA_NAME_SEPARATOR)
    if separator and rest and prefix.lower() in schemas:
        return prefix, rest
    return MAIN_SCHEMA, table_name


def catalog_relations(connection: Any) -> tuple[tuple[str, str, str, str], ...]:
    """Return (schema, name, physical name, relation type) for every user table and view."""

    schemas: frozenset[str] = registered_schemas(connection)
    rows: list[tuple[Any, ...]] = connection.execute(
        "SELECT name, type FROM sqlite_schema WHERE type IN ('table', 'view') ORDER BY name"
    ).fetchall()
    relations: list[tuple[str, str, str, str]] = []
    row: tuple[Any, ...]
    for row in rows:
        table_name: str = str(row[0])
        if table_name.lower().startswith(SQLITE_INTERNAL_PREFIX) or (
            table_name == SCHEMA_REGISTRY_TABLE
        ):
            continue
        schema: str
        name: str
        schema, name = logical_location(table_name=table_name, schemas=schemas)
        relation_type: str = (
            VIEW_RELATION_TYPE if row[1] == SQLITE_VIEW_TYPE else BASE_TABLE_RELATION_TYPE
        )
        relations.append((schema, name, table_name, relation_type))
    return tuple(relations)


def relation_columns(*, connection: Any, table_name: str) -> tuple[ColumnInfo, ...]:
    """Return declared column types, sampling stored values for untyped columns."""

    rows: list[tuple[Any, ...]] = connection.execute(
        f"PRAGMA table_xinfo({quote_identifier(table_name)})"
    ).fetchall()
    visible: list[tuple[str, str]] = [
        (str(row[1]), str(row[2] or "")) for row in rows if not row[6]
    ]
    untyped: tuple[str, ...] = tuple(name for name, declared in visible if not declared)
    sampled: dict[str, str] = _sample_value_types(
        connection=connection, table_name=table_name, columns=untyped
    )
    return tuple(
        ColumnInfo(name=name, type=reported_type(declared) if declared else sampled[name])
        for name, declared in visible
    )


def reported_type(declared: str) -> str:
    """Report a decimal stored as canonical text under its decimal type."""

    upper: str = declared.upper()
    if upper.startswith(DECIMAL_TEXT_TYPE_PREFIX) and upper[
        len(DECIMAL_TEXT_TYPE_PREFIX) :
    ].startswith(DECIMAL_TYPE_NAMES):
        return declared[len(DECIMAL_TEXT_TYPE_PREFIX) :]
    return declared


def view_body(definition: str) -> str:
    """Return the SELECT of a stored CREATE VIEW statement."""

    match: re.Match[str] | None = _VIEW_BODY.match(definition)
    return definition if match is None else match.group(1).strip()


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sample_value_types(
    *, connection: Any, table_name: str, columns: tuple[str, ...]
) -> dict[str, str]:
    if not columns:
        return {}
    relation: str = quote_identifier(table_name)
    projections: str = ", ".join(
        f"(SELECT typeof({quote_identifier(column)}) FROM {relation} "
        f"WHERE {quote_identifier(column)} IS NOT NULL LIMIT 1)"
        for column in columns
    )
    row: tuple[Any, ...] = connection.execute(f"SELECT {projections}").fetchone()
    return {
        column: TYPEOF_TYPE_NAMES.get(str(value), UNTYPED_COLUMN_TYPE)
        for column, value in zip(columns, row, strict=True)
    }
