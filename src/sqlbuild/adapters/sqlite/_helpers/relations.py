"""Relation registry upkeep and view renames, applied as the adapter executes DDL."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.sqlite._helpers.catalog import registry_exists, unquote_relation, view_body
from sqlbuild.adapters.sqlite.constants import MAIN_SCHEMA, RELATION_REGISTRY_TABLE

_NAME: str = r"((?:main\.)?(?:\"(?:[^\"]|\"\")+\"|[^\s(;\"]+))"
_CREATE: re.Pattern[str] = re.compile(
    r"^\s*CREATE\s+(?:UNIQUE\s+)?(TEMP\s+|TEMPORARY\s+)?(?:TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    + _NAME,
    re.IGNORECASE,
)
_DROP: re.Pattern[str] = re.compile(
    r"^\s*DROP\s+(?:TABLE|VIEW)\s+(?:IF\s+EXISTS\s+)?" + _NAME, re.IGNORECASE
)
_RENAME_TABLE: re.Pattern[str] = re.compile(
    r"^\s*ALTER\s+TABLE\s+" + _NAME + r"\s+RENAME\s+TO\s+" + _NAME + r"\s*;?\s*$",
    re.IGNORECASE,
)
_RENAME_VIEW: re.Pattern[str] = re.compile(
    r"^\s*ALTER\s+VIEW\s+" + _NAME + r"\s+RENAME\s+TO\s+" + _NAME + r"\s*;?\s*$",
    re.IGNORECASE,
)
_TEMP_PREFIX: str = "temp."


def split_rename_view(sql: str) -> tuple[str, str] | None:
    """Return (origin, destination) of an `ALTER VIEW ... RENAME TO ...` statement."""

    match: re.Match[str] | None = _RENAME_VIEW.match(sql)
    if match is None:
        return None
    return match.group(1), match.group(2)


def rename_view(*, connection: Any, origin: str, destination: str) -> Any:
    """Recreate a view under its new name, since SQLite cannot alter a view."""

    row: tuple[Any, ...] | None = connection.execute_with(
        sql="SELECT sql FROM sqlite_schema WHERE type = 'view' AND lower(name) = lower(?)",
        parameters=(unquote_relation(origin),),
    ).fetchone()
    if row is None:
        raise AdapterUserError(message=f"SQLite view '{origin}' does not exist")
    connection.execute(f"DROP VIEW {origin}")
    return connection.execute(f"CREATE VIEW {destination} AS {view_body(str(row[0]))}")


def relation_changes(sql: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the physical names one statement removes and creates."""

    rename: re.Match[str] | None = _RENAME_TABLE.match(sql) or _RENAME_VIEW.match(sql)
    if rename is not None:
        return (unquote_relation(rename.group(1)),), (unquote_relation(rename.group(2)),)
    create: re.Match[str] | None = _CREATE.match(sql)
    if create is not None and create.group(1) is None and not _is_temp(create.group(2)):
        return (), (unquote_relation(create.group(2)),)
    drop: re.Match[str] | None = _DROP.match(sql)
    if drop is not None and not _is_temp(drop.group(1)):
        return (unquote_relation(drop.group(1)),), ()
    return (), ()


def record_relation_changes(
    *,
    connection: Any,
    removed: tuple[str, ...],
    added: tuple[str, ...],
    locate: Callable[[str], tuple[str, str] | None],
) -> None:
    """Keep the registry's (schema, name) of every schema relation SQLBuild created."""

    rows: list[tuple[str, str, str]] = []
    physical: str
    for physical in added:
        location: tuple[str, str] | None = locate(physical)
        if location is not None and location[0].lower() != MAIN_SCHEMA:
            rows.append((physical, location[0], location[1]))
    if rows:
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {RELATION_REGISTRY_TABLE} (physical_name TEXT PRIMARY "
            "KEY COLLATE NOCASE, schema_name TEXT NOT NULL, relation_name TEXT NOT NULL)"
        )
    elif not registry_exists(connection):
        return
    for physical in (*removed, *added):
        connection.execute_with(
            sql=f"DELETE FROM {RELATION_REGISTRY_TABLE} WHERE physical_name = ?",
            parameters=(physical,),
        )
    row: tuple[str, str, str]
    for row in rows:
        connection.execute_with(
            sql=(
                f"INSERT INTO {RELATION_REGISTRY_TABLE} (physical_name, schema_name, "
                "relation_name) VALUES (?, ?, ?)"
            ),
            parameters=row,
        )


def _is_temp(name: str) -> bool:
    return name.lower().startswith(_TEMP_PREFIX)
