"""Helpers for Snowflake adapter unit tests."""

from __future__ import annotations

import sys
from itertools import cycle, islice
from types import ModuleType
from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo


class FakeSnowflakeDescribeCursor:
    """Cursor double exposing Snowflake-style description metadata."""

    def __init__(self, description: tuple[tuple[str], ...]) -> None:
        self.description: tuple[tuple[str], ...] = description
        self.executed_sql: str | None = None
        self.executemany_sql: str | None = None
        self.executemany_rows: list[tuple[object, ...]] = []
        self.closed: bool = False

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        self.executemany_sql = sql
        self.executemany_rows = rows

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeDescribeConnection:
    """Connection double returning a preconfigured describe cursor."""

    def __init__(self, cursor: FakeSnowflakeDescribeCursor) -> None:
        self._cursor: FakeSnowflakeDescribeCursor = cursor
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> Any:
        self.executed_sql.append(sql)
        return self._cursor

    def cursor(self) -> Any:
        return self._cursor


class FakeSnowflakeMetadataCursor:
    """Cursor double exposing Snowflake-style metadata rows."""

    def __init__(
        self,
        row: tuple[object, ...] | None = None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.row: tuple[object, ...] | None = row
        self.rows: list[tuple[object, ...]] = rows or []
        self.executed_sql: str | None = None
        self.executed_params: tuple[object, ...] | None = None
        self.closed: bool = False

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        self.executed_sql = sql
        self.executed_params = params

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeMetadataConnection:
    """Connection double returning a preconfigured metadata cursor."""

    def __init__(self, cursor: FakeSnowflakeMetadataCursor) -> None:
        self._cursor: FakeSnowflakeMetadataCursor = cursor

    def cursor(self) -> FakeSnowflakeMetadataCursor:
        return self._cursor


class FakeSnowflakeMetadataSequenceConnection:
    """Connection double returning one metadata cursor per exact relation query."""

    def __init__(self, cursors: tuple[FakeSnowflakeMetadataCursor, ...]) -> None:
        self._cursors: list[FakeSnowflakeMetadataCursor] = list(cursors)
        self.returned_cursors: list[FakeSnowflakeMetadataCursor] = []

    def cursor(self) -> FakeSnowflakeMetadataCursor:
        cursor: FakeSnowflakeMetadataCursor = self._cursors.pop(0)
        self.returned_cursors.append(cursor)
        return cursor


def build_qualified_column_relations(*, count: int) -> tuple[RelationInfo, ...]:
    """Build mixed table/view relations with a duplicate name across two schemas."""

    names: tuple[str, ...] = (
        "SHARED",
        "SHARED",
        *(f"RELATION_{index}" for index in range(2, count)),
    )
    schemas: tuple[str, ...] = tuple(islice(cycle(("SCHEMA_A", "SCHEMA_B")), count))
    relation_types: tuple[str, ...] = tuple(
        islice(cycle(("BASE TABLE", "VIEW")), count)
    )
    return tuple(
        RelationInfo(
            database="RACING",
            schema=schema,
            name=name,
            relation_type=relation_type,
        )
        for name, schema, relation_type in zip(names, schemas, relation_types, strict=True)
    )


def build_show_columns_rows(*, relation: RelationInfo) -> list[tuple[object, ...]]:
    """Build documented SHOW COLUMNS rows for numeric and text columns."""

    return [
        (
            relation.name,
            relation.schema,
            "ID",
            '{"type":"FIXED","precision":20,"scale":4,"nullable":false}',
            False,
            None,
            "COLUMN",
            None,
            None,
            relation.database,
        ),
        (
            relation.name,
            relation.schema,
            "LABEL",
            '{"type":"TEXT","length":128,"byteLength":512,"nullable":true}',
            True,
            None,
            "COLUMN",
            None,
            None,
            relation.database,
        ),
    ]


def build_bulk_columns_rows(
    *, relations: tuple[RelationInfo, ...]
) -> list[tuple[object, ...]]:
    """Build INFORMATION_SCHEMA rows equivalent to the exact SHOW fixtures."""

    rows: list[tuple[object, ...]] = []
    relation: RelationInfo
    for relation in relations:
        rows.extend(
            (
                (relation.database, relation.schema, relation.name, "ID", "NUMBER", 20, 4, None),
                (
                    relation.database,
                    relation.schema,
                    relation.name,
                    "LABEL",
                    "TEXT",
                    None,
                    None,
                    128,
                ),
            )
        )
    return rows


def expected_qualified_columns(
    *, relations: tuple[RelationInfo, ...]
) -> dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]]:
    """Build normalized expected columns keyed by physical identity."""

    return {
        relation.identity: (
            ColumnInfo(name="id", type="NUMBER(20,4)"),
            ColumnInfo(name="label", type="VARCHAR(128)"),
        )
        for relation in relations
    }


def build_bulk_sequence_connection(
    *, relations: tuple[RelationInfo, ...], chunk_size: int
) -> FakeSnowflakeMetadataSequenceConnection:
    """Build one bulk metadata cursor per expected relation chunk."""

    cursors: list[FakeSnowflakeMetadataCursor] = []
    chunk_start: int
    for chunk_start in range(0, len(relations), chunk_size):
        chunk: tuple[RelationInfo, ...] = relations[chunk_start : chunk_start + chunk_size]
        cursors.append(
            FakeSnowflakeMetadataCursor(rows=build_bulk_columns_rows(relations=chunk))
        )
    return FakeSnowflakeMetadataSequenceConnection(tuple(cursors))


def describe_equivalent_numeric_relation(
    connection: object, relation: str
) -> tuple[ColumnInfo, ...]:
    del connection
    columns_by_relation: dict[str, tuple[ColumnInfo, ...]] = {
        "left_relation": (ColumnInfo(name="id", type="NUMBER(38,0)"),),
        "right_relation": (ColumnInfo(name="id", type="DECIMAL(38,0)"),),
    }
    return columns_by_relation[relation]


class FakeSnowflakeRawConnection:
    """Raw connector connection double for connect() tests."""

    def cursor(self) -> Any:
        raise AssertionError("connect test should not execute SQL")

    def close(self) -> None:
        pass


def install_fake_snowflake_connector(monkeypatch: Any) -> dict[str, object]:
    """Install a fake optional snowflake.connector module and capture connect kwargs."""

    captured_kwargs: dict[str, object] = {}
    snowflake_module: ModuleType = ModuleType("snowflake")
    connector_module: ModuleType = ModuleType("snowflake.connector")

    def connect(**kwargs: object) -> FakeSnowflakeRawConnection:
        captured_kwargs.update(kwargs)
        return FakeSnowflakeRawConnection()

    connector_module.__dict__["connect"] = connect
    snowflake_module.__dict__["connector"] = connector_module
    monkeypatch.setitem(sys.modules, "snowflake", snowflake_module)
    monkeypatch.setitem(sys.modules, "snowflake.connector", connector_module)
    return captured_kwargs
