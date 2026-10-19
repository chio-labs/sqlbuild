from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse._test_types import (
    ClickHousePhysicalLayoutE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    active_parts_by_partition,
    build_partitioned_events_project_files,
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


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHousePhysicalLayoutE2ETestCase(
            description="a March window rewrites only March",
            first_events=(
                "(1, 10, '2026-01-05 08:00:00'), (2, 20, '2026-01-20 09:00:00'), "
                "(3, 30, '2026-02-03 10:00:00'), (4, 40, '2026-02-17 11:00:00'), "
                "(5, 50, '2026-03-01 12:00:00')"
            ),
            later_events="(6, 60, '2026-03-09 08:00:00'), (7, 70, '2026-03-20 09:00:00')",
            expected_create_fragments=(
                "ENGINE = ReplacingMergeTree(version)",
                "PARTITION BY toYYYYMM(event_time)",
                "PRIMARY KEY event_id",
                "ORDER BY (event_id, event_time)",
                "index_granularity = 4096",
            ),
            expected_partition_rewrites={"202601": False, "202602": False, "202603": True},
            expected_totals=(("7", "280"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partitioned_layout_when_building_incrementally_then_only_touched_partitions_change(
    tmp_path: Path,
    test_case: ClickHousePhysicalLayoutE2ETestCase,
    clickhouse_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqb_layout")
    config: dict[str, object] = clickhouse_e2e_config
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="clickhouse_layout",
        repo_files=build_partitioned_events_project_files(schema_name=schema_name, config=config),
    )
    create_clickhouse_schema(config=config, schema_name=schema_name)
    execute_clickhouse_sql(
        config=config,
        statements=(
            f"CREATE TABLE {schema_name}.raw_events (event_id Int64, amount Int64, "
            "event_time DateTime64(6, 'UTC')) ENGINE = MergeTree ORDER BY event_id",
            f"INSERT INTO {schema_name}.raw_events VALUES {test_case.first_events}",
        ),
    )
    try:
        first: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        assert first.returncode == 0, first.stdout + first.stderr
        create_sql: str = str(
            fetch_clickhouse_rows(
                config=config,
                sql="SELECT create_table_query FROM system.tables "
                f"WHERE database = '{schema_name}' AND name = 'events'",
            )[0][0]
        )
        assert [fragment in create_sql for fragment in test_case.expected_create_fragments] == [
            True
        ] * len(test_case.expected_create_fragments), create_sql
        execute_clickhouse_sql(
            config=config, statements=(f"SYSTEM STOP MERGES {schema_name}.events",)
        )
        before: dict[str, tuple[str, ...]] = active_parts_by_partition(
            config=config, schema_name=schema_name, table="events"
        )
        execute_clickhouse_sql(
            config=config,
            statements=(f"INSERT INTO {schema_name}.raw_events VALUES {test_case.later_events}",),
        )

        second: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )

        assert second.returncode == 0, second.stdout + second.stderr
        after: dict[str, tuple[str, ...]] = active_parts_by_partition(
            config=config, schema_name=schema_name, table="events"
        )
        assert {partition: after[partition] != parts for partition, parts in before.items()} == (
            test_case.expected_partition_rewrites
        )
        assert stringify_warehouse_rows(
            fetch_clickhouse_rows(
                config=config,
                sql=f"SELECT count(), sum(amount) FROM {schema_name}.events FINAL",
            )
        ) == (test_case.expected_totals)
    finally:
        cleanup_clickhouse_schema(config=config, schema_name=schema_name)
