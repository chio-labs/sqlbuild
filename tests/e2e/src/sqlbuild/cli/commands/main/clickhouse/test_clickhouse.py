from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse._test_types import (
    ClickHouseBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    build_orders_project_files,
    build_unique_schema_name,
    cleanup_clickhouse_schema,
    create_clickhouse_schema,
    execute_clickhouse_sql,
    fetch_clickhouse_rows,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
    stringify_warehouse_rows,
)

_FIRST_EVENTS: str = (
    "(1, 1, 100, '2026-01-01 08:00:00'), (2, 2, 200, '2026-01-01 09:00:00'), "
    "(3, 1, 50, '2026-01-02 10:00:00'), (4, 3, 300, '2026-01-02 11:00:00'), "
    "(5, 2, 25, '2026-01-03 12:00:00'), (6, 3, 75, '2026-01-04 13:00:00')"
)
_LATER_EVENTS: str = "(7, 1, 10, '2026-01-05 08:00:00'), (8, 2, 20, '2026-01-06 09:00:00')"


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseBuildE2ETestCase(
            description="views, tables, seeds, functions, merge and concurrent microbatches",
            expected_customer_rows=(
                ("1", "north", "150", "75.0"),
                ("2", "south", "225", "112.5"),
                ("3", "east", "375", "187.5"),
            ),
            expected_order_totals=(("6", "750"),),
            expected_name_rows=(("1", "ada lovelace"), ("2", "bo"), ("3", "cy")),
            expected_daily_rows_after_first_build=(
                ("2026-01-01", "2"),
                ("2026-01-02", "2"),
                ("2026-01-03", "1"),
                ("2026-01-04", "1"),
            ),
            expected_daily_rows_after_second_build=(
                ("2026-01-01", "2"),
                ("2026-01-02", "2"),
                ("2026-01-03", "1"),
                ("2026-01-04", "1"),
                ("2026-01-05", "1"),
                ("2026-01-06", "1"),
            ),
            expected_latest_rows=(
                ("1", "3", "2026-01-05 08:00:00"),
                ("2", "3", "2026-01-06 09:00:00"),
                ("3", "2", "2026-01-04 13:00:00"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_orders_project_when_building_twice_on_clickhouse_then_every_strategy_lands(
    tmp_path: Path,
    test_case: ClickHouseBuildE2ETestCase,
    clickhouse_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqb_orders")
    config: dict[str, object] = clickhouse_e2e_config
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="clickhouse_orders",
        repo_files=build_orders_project_files(schema_name=schema_name, config=config),
    )
    create_clickhouse_schema(config=config, schema_name=schema_name)
    execute_clickhouse_sql(
        config=config,
        statements=(
            f"CREATE TABLE {schema_name}.raw_events (event_id Int64, customer_id Int64, "
            "amount Int64, event_time DateTime64(6, 'UTC')) ENGINE = MergeTree ORDER BY event_id",
            f"INSERT INTO {schema_name}.raw_events VALUES {_FIRST_EVENTS}",
            f"CREATE TABLE {schema_name}.raw_customers (customer_id Int64, "
            "customer_name String, version Int64) ENGINE = ReplacingMergeTree(version) "
            "ORDER BY customer_id",
            f"SYSTEM STOP MERGES {schema_name}.raw_customers",
            f"INSERT INTO {schema_name}.raw_customers VALUES (1, 'ada', 1), (2, 'bo', 1)",
            f"INSERT INTO {schema_name}.raw_customers VALUES (1, 'ada lovelace', 2), (3, 'cy', 1)",
        ),
    )
    try:
        first: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        assert first.returncode == 0, first.stdout + first.stderr
        assert stringify_warehouse_rows(
            fetch_clickhouse_rows(
                config=config,
                sql=f"SELECT customer_id, region_name, total_amount, half_total "
                f"FROM {schema_name}.customer_totals ORDER BY customer_id",
            )
        ) == (test_case.expected_customer_rows)
        assert stringify_warehouse_rows(
            fetch_clickhouse_rows(
                config=config,
                sql=f"SELECT count(), sum(amount) FROM {schema_name}.stg_events",
            )
        ) == (test_case.expected_order_totals)
        assert fetch_clickhouse_rows(
            config=config, sql=f"SELECT count() FROM {schema_name}.raw_customers"
        ) == ((4,),)
        assert stringify_warehouse_rows(
            fetch_clickhouse_rows(
                config=config,
                sql=f"SELECT customer_id, customer_name FROM {schema_name}.customer_names "
                "ORDER BY customer_id",
            )
        ) == (test_case.expected_name_rows)
        daily_sql: str = (
            f"SELECT toDate(event_time) AS day, count() FROM {schema_name}.daily_events "
            "GROUP BY day ORDER BY day"
        )
        assert stringify_warehouse_rows(fetch_clickhouse_rows(config=config, sql=daily_sql)) == (
            test_case.expected_daily_rows_after_first_build
        )

        execute_clickhouse_sql(
            config=config,
            statements=(f"INSERT INTO {schema_name}.raw_events VALUES {_LATER_EVENTS}",),
        )
        second: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        assert second.returncode == 0, second.stdout + second.stderr
        assert "Concurrent microbatch execution is enabled" in second.stdout + second.stderr
        assert stringify_warehouse_rows(fetch_clickhouse_rows(config=config, sql=daily_sql)) == (
            test_case.expected_daily_rows_after_second_build
        )
        assert stringify_warehouse_rows(
            fetch_clickhouse_rows(
                config=config,
                sql=f"SELECT customer_id, event_count, toString(toDateTime(last_event_time)) "
                f"FROM {schema_name}.customer_latest ORDER BY customer_id",
            )
        ) == (test_case.expected_latest_rows)
        artifacts: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
            config=config,
            sql=f"SELECT name FROM system.tables WHERE database = '{schema_name}' "
            "AND (name LIKE '%__sqb_%' OR name LIKE '__sqb_%')",
        )
        assert artifacts == ()
        state_engines: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
            config=config,
            sql=f"SELECT DISTINCT engine FROM system.tables WHERE database = '{schema_name}' "
            "AND startsWith(name, '_sqlbuild_')",
        )
        assert state_engines == (("MergeTree",),)

        query: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "query",
                f"SELECT sum(total_amount) AS revenue FROM {schema_name}.customer_totals",
            ),
            project_dir=project_dir,
        )
        assert query.returncode == 0, query.stdout + query.stderr
        assert "revenue" in query.stdout and "780" in query.stdout
    finally:
        cleanup_clickhouse_schema(config=config, schema_name=schema_name)
