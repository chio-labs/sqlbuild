"""Helpers that execute adapter-rendered snapshot SQL on DuckDB over shared scenarios.

DuckDB runs the SQL rendered by the DuckDB, MotherDuck, Postgres, BigQuery, Snowflake and
Databricks adapters. The only shims are identifier quoting for BigQuery and a pinned execution
clock so current-state histories are deterministic; neither changes statement semantics. SQL
Server renders T-SQL that DuckDB cannot parse, so it is covered by rendering assertions only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import duckdb

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import SnapshotChangeTarget
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.spec.contracts.types import TableType
from tests.integration.src.sqlbuild.adapters.snapshot_sql_rendering._test_types import (
    SnapshotExecutionTestCase,
)


@dataclass(frozen=True)
class SnapshotExecutionAdapter:
    """Adapter whose rendered snapshot SQL is executed on DuckDB."""

    name: str
    adapter_type: type[BaseAdapter]
    normalize_sql: Callable[[str], str]


@dataclass(frozen=True)
class SnapshotExecutionKind:
    """Snapshot configuration family shared by execution scenarios."""

    source_select_sql: Callable[[tuple[object, ...]], str]
    render_initial: Callable[[BaseAdapter], tuple[str, ...]]
    render_apply: Callable[[BaseAdapter], tuple[str, ...]]
    history_sql: str


@dataclass(frozen=True)
class SnapshotExecutionScenario:
    """Source rows per build and the history every adapter must produce."""

    description: str
    kind: SnapshotExecutionKind
    builds: tuple[tuple[tuple[object, ...], ...], ...]
    expected_history: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class SnapshotExecutionRun:
    """One adapter executing one scenario through incremental builds or one initial build."""

    adapter: SnapshotExecutionAdapter
    scenario: SnapshotExecutionScenario
    path: str
    builds: tuple[tuple[tuple[object, ...], ...], ...]


_TARGET: str = "snapshot_target"
_SOURCE: str = "snapshot_source"
FIRST_CLOCK_DAY: int = 20
_KEY: tuple[str, ...] = ("customer_id",)


def _timestamp(day: object) -> str:
    return f"TIMESTAMP '2026-01-{int(str(day)):02d}'"


def _check_history_row_sql(row: tuple[object, ...]) -> str:
    return (
        f"SELECT {row[0]} AS customer_id, '{row[1]}' AS status, {_timestamp(row[2])} AS observed_at"
    )


def _timestamp_history_row_sql(row: tuple[object, ...]) -> str:
    return (
        f"SELECT {row[0]} AS customer_id, '{row[1]}' AS plan, "
        f"{_timestamp(row[2])} AS updated_at, {_timestamp(row[3])} AS observed_at"
    )


def _current_check_row_sql(row: tuple[object, ...]) -> str:
    return f"SELECT {row[0]} AS customer_id, '{row[1]}' AS status"


def _current_timestamp_row_sql(row: tuple[object, ...]) -> str:
    return f"SELECT {row[0]} AS customer_id, '{row[1]}' AS plan, {_timestamp(row[2])} AS updated_at"


def _historical_check_initial(adapter: BaseAdapter, hard_deletes: bool) -> tuple[str, ...]:
    return adapter.render_create_initial_historical_check_snapshot_destination(
        table_type=TableType.PERMANENT,
        destination=_TARGET,
        origin=_SOURCE,
        unique_key=_KEY,
        check_columns=("status",),
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "status", "observed_at"),
        invalidate_hard_deletes=hard_deletes,
    )


def _historical_check_apply(adapter: BaseAdapter, hard_deletes: bool) -> tuple[str, ...]:
    return adapter.render_apply_historical_check_snapshot_changes(
        destination=_TARGET,
        origin=_SOURCE,
        unique_key=_KEY,
        check_columns=("status",),
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "status", "observed_at"),
        invalidate_hard_deletes=hard_deletes,
    )


def _historical_timestamp_initial(adapter: BaseAdapter, hard_deletes: bool) -> tuple[str, ...]:
    return adapter.render_create_initial_historical_timestamp_snapshot_destination(
        table_type=TableType.PERMANENT,
        destination=_TARGET,
        origin=_SOURCE,
        unique_key=_KEY,
        updated_at_column="updated_at",
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "plan", "updated_at", "observed_at"),
        invalidate_hard_deletes=hard_deletes,
    )


def _historical_timestamp_apply(adapter: BaseAdapter, hard_deletes: bool) -> tuple[str, ...]:
    return adapter.render_apply_historical_timestamp_snapshot_changes(
        destination=_TARGET,
        origin=_SOURCE,
        unique_key=_KEY,
        updated_at_column="updated_at",
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "plan", "updated_at", "observed_at"),
        invalidate_hard_deletes=hard_deletes,
    )


def _current_initial(
    adapter: BaseAdapter, strategy: str, updated_at_column: str | None
) -> tuple[str, ...]:
    return adapter.render_create_initial_snapshot_destination(
        table_type=TableType.PERMANENT,
        destination=_TARGET,
        origin=_SOURCE,
        snapshot_strategy=strategy,
        updated_at_column=updated_at_column,
        observed_at_column=None,
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        initial_valid_from=None,
    )


def _current_timestamp_apply(adapter: BaseAdapter, hard_deletes: bool) -> tuple[str, ...]:
    return adapter.render_apply_timestamp_snapshot_changes(
        destination=_TARGET,
        origin=_SOURCE,
        unique_key=_KEY,
        updated_at_column="updated_at",
        observed_at_column=None,
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        initial_valid_from=None,
        output_columns=("customer_id", "plan", "updated_at"),
        invalidate_hard_deletes=hard_deletes,
    )


def _current_check_apply(adapter: BaseAdapter, hard_deletes: bool) -> tuple[str, ...]:
    return adapter.render_apply_check_snapshot_changes(
        target=SnapshotChangeTarget(
            destination=_TARGET,
            origin=_SOURCE,
            unique_key=_KEY,
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "status"),
        ),
        check_columns=("status",),
        updated_at_column=None,
        observed_at_column=None,
        initial_valid_from=None,
        invalidate_hard_deletes=hard_deletes,
    )


def _history_sql(value_column: str) -> str:
    return (
        f"SELECT customer_id, {value_column}, day(valid_from), day(valid_to) "
        f"FROM {_TARGET} ORDER BY customer_id, valid_from"
    )


def _unquote_backticks(sql: str) -> str:
    return sql.replace("`", '"')


def _unchanged(sql: str) -> str:
    return sql


HISTORICAL_CHECK: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_check_history_row_sql,
    render_initial=lambda adapter: _historical_check_initial(adapter, False),
    render_apply=lambda adapter: _historical_check_apply(adapter, False),
    history_sql=_history_sql("status"),
)
HISTORICAL_CHECK_HARD_DELETES: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_check_history_row_sql,
    render_initial=lambda adapter: _historical_check_initial(adapter, True),
    render_apply=lambda adapter: _historical_check_apply(adapter, True),
    history_sql=_history_sql("status"),
)
HISTORICAL_TIMESTAMP: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_timestamp_history_row_sql,
    render_initial=lambda adapter: _historical_timestamp_initial(adapter, False),
    render_apply=lambda adapter: _historical_timestamp_apply(adapter, False),
    history_sql=_history_sql("plan"),
)
HISTORICAL_TIMESTAMP_HARD_DELETES: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_timestamp_history_row_sql,
    render_initial=lambda adapter: _historical_timestamp_initial(adapter, True),
    render_apply=lambda adapter: _historical_timestamp_apply(adapter, True),
    history_sql=_history_sql("plan"),
)
CURRENT_TIMESTAMP: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_current_timestamp_row_sql,
    render_initial=lambda adapter: _current_initial(adapter, "timestamp", "updated_at"),
    render_apply=lambda adapter: _current_timestamp_apply(adapter, False),
    history_sql=_history_sql("plan"),
)
CURRENT_TIMESTAMP_HARD_DELETES: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_current_timestamp_row_sql,
    render_initial=lambda adapter: _current_initial(adapter, "timestamp", "updated_at"),
    render_apply=lambda adapter: _current_timestamp_apply(adapter, True),
    history_sql=_history_sql("plan"),
)
CURRENT_CHECK_HARD_DELETES: SnapshotExecutionKind = SnapshotExecutionKind(
    source_select_sql=_current_check_row_sql,
    render_initial=lambda adapter: _current_initial(adapter, "check", None),
    render_apply=lambda adapter: _current_check_apply(adapter, True),
    history_sql=_history_sql("status"),
)

ADAPTERS: tuple[SnapshotExecutionAdapter, ...] = (
    SnapshotExecutionAdapter(name="duckdb", adapter_type=DuckDbAdapter, normalize_sql=_unchanged),
    SnapshotExecutionAdapter(
        name="motherduck", adapter_type=MotherDuckAdapter, normalize_sql=_unchanged
    ),
    SnapshotExecutionAdapter(
        name="postgres", adapter_type=PostgresAdapter, normalize_sql=_unchanged
    ),
    SnapshotExecutionAdapter(
        name="bigquery", adapter_type=BigQueryAdapter, normalize_sql=_unquote_backticks
    ),
    SnapshotExecutionAdapter(
        name="snowflake", adapter_type=SnowflakeAdapter, normalize_sql=_unchanged
    ),
    SnapshotExecutionAdapter(
        name="databricks", adapter_type=DatabricksAdapter, normalize_sql=_unchanged
    ),
)

INVARIANT_VIOLATIONS_SQL: str = (
    "SELECT "
    f"(SELECT COUNT(*) FROM (SELECT customer_id FROM {_TARGET} WHERE valid_to IS NULL "
    "GROUP BY customer_id HAVING COUNT(*) > 1)), "
    f"(SELECT COUNT(*) FROM {_TARGET} WHERE valid_to IS NOT NULL AND valid_from >= valid_to), "
    f"(SELECT COUNT(*) FROM {_TARGET} AS left_row JOIN {_TARGET} AS right_row "
    "ON left_row.customer_id = right_row.customer_id "
    "AND left_row.valid_from < right_row.valid_from "
    "AND right_row.valid_from < COALESCE(left_row.valid_to, TIMESTAMP '9999-12-31'))"
)


def build_execution_runs(
    *,
    incremental_scenarios: tuple[SnapshotExecutionScenario, ...],
    full_history_scenarios: tuple[SnapshotExecutionScenario, ...],
) -> tuple[SnapshotExecutionRun, ...]:
    """Run every scenario on every adapter, and historical scenarios as one initial build."""

    runs: list[SnapshotExecutionRun] = []
    adapter: SnapshotExecutionAdapter
    scenario: SnapshotExecutionScenario
    for adapter in ADAPTERS:
        for scenario in incremental_scenarios:
            runs.append(
                SnapshotExecutionRun(
                    adapter=adapter,
                    scenario=scenario,
                    path="incremental builds",
                    builds=scenario.builds,
                )
            )
        for scenario in full_history_scenarios:
            runs.append(
                SnapshotExecutionRun(
                    adapter=adapter,
                    scenario=scenario,
                    path="initial full history",
                    builds=(scenario.builds[-1],),
                )
            )
    return tuple(runs)


def run_snapshot_builds(
    test_case: SnapshotExecutionTestCase,
) -> tuple[tuple[tuple[object, ...], ...], tuple[object, ...] | None]:
    """Execute each build's rendered statements and return the history and invariant counts."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect()
    _run_build(
        connection=connection,
        test_case=test_case,
        rows=test_case.builds[0],
        render=test_case.render_initial,
        day=FIRST_CLOCK_DAY,
    )
    build_index: int
    rows: tuple[tuple[object, ...], ...]
    for build_index, rows in enumerate(test_case.builds[1:], start=1):
        _run_build(
            connection=connection,
            test_case=test_case,
            rows=rows,
            render=test_case.render_apply,
            day=FIRST_CLOCK_DAY + build_index,
        )
    history: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.history_sql).fetchall()
    )
    violations: tuple[object, ...] | None = connection.execute(INVARIANT_VIOLATIONS_SQL).fetchone()
    connection.close()
    return history, violations


def _pinned_clock_adapter(adapter_type: type[BaseAdapter], day: int) -> BaseAdapter:
    clock_sql: str = _timestamp(day)
    pinned_type: type[BaseAdapter] = type(
        f"PinnedClock{adapter_type.__name__}",
        (adapter_type,),
        {"render_current_timestamp": lambda _self: clock_sql},
    )
    return pinned_type()


def _run_build(
    *,
    connection: duckdb.DuckDBPyConnection,
    test_case: SnapshotExecutionTestCase,
    rows: tuple[tuple[object, ...], ...],
    render: Callable[[BaseAdapter], tuple[str, ...]],
    day: int,
) -> None:
    source_sql: str = " UNION ALL ".join(test_case.source_select_sql(row) for row in rows)
    connection.execute(f"CREATE OR REPLACE TABLE {_SOURCE} AS {source_sql}")
    adapter: BaseAdapter = _pinned_clock_adapter(test_case.adapter_type, day)
    statement: str
    for statement in render(adapter):
        connection.execute(test_case.normalize_sql(statement))
