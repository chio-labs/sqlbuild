"""Helpers for diff executor integration tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.diff.models import DiffExecutionOptions, FullDiffSizeLimits


class RecordingDuckDbAdapter(DuckDbAdapter):
    """DuckDB adapter that records every executed statement."""

    def __init__(self) -> None:
        super().__init__()
        self.statements: list[str] = []

    def execute(self, *, connection: Any, sql: str) -> Any:
        self.statements.append(sql)
        return super().execute(connection=connection, sql=sql)


@dataclass(frozen=True)
class FakeDestination:
    """Compiled relation location."""

    database: str | None
    schema: str | None
    name: str
    qualified_name: str | None = None


@dataclass(frozen=True)
class FakeConfig:
    """Compiled model configuration values."""

    values: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FakeModel:
    """Compiled model with a destination."""

    name: str
    destination: FakeDestination
    config: FakeConfig


@dataclass(frozen=True)
class FakeProject:
    """Compiled project models."""

    models: tuple[FakeModel, ...]


def orders_project(schema: str) -> FakeProject:
    """Return a project whose orders model lives in the given schema."""

    return FakeProject(
        models=(
            FakeModel(
                name="orders",
                destination=FakeDestination(database=None, schema=schema, name="orders"),
                config=FakeConfig(values={"unique_key": ["order_id"]}),
            ),
        )
    )


def prod_dev_orders_connection(*, right_relation_kind: str) -> duckdb.DuckDBPyConnection:
    """Return a connection with prod.orders (6 rows) and dev.orders (8 rows)."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    connection.execute("CREATE SCHEMA prod")
    connection.execute("CREATE SCHEMA dev")
    connection.execute(
        "CREATE TABLE prod.orders AS SELECT range AS order_id, range * 10 AS amount FROM range(6)"
    )
    connection.execute(
        f"CREATE {right_relation_kind} dev.orders AS "
        "SELECT range AS order_id, range * 10 AS amount FROM range(8)"
    )
    return connection


def guarded_full_options(
    *, left_max_rows: int | None, right_max_rows: int | None
) -> DiffExecutionOptions:
    """Return guarded full-diff options for prod against dev."""

    return DiffExecutionOptions(
        schema_only=False,
        full_size_limits=FullDiffSizeLimits(
            left_target="prod",
            right_target="dev",
            left_max_rows=left_max_rows,
            right_max_rows=right_max_rows,
        ),
    )
