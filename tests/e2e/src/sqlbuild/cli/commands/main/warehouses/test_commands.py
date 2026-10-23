"""Python node, freshness and scenario command scenarios shared by every real warehouse."""

from __future__ import annotations

import subprocess
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    assert_optional_local_replay_rows,
    build_real_warehouse_local_replay_project_files,
    build_real_warehouse_remote_scenario_project_files,
    maybe_corrupt_scenario_snapshot_dialect,
)
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses._test_types import (
    CliTestCase,
    NodeResultTestCase,
    ScenarioLocalReplayTestCase,
    ScenarioRemoteTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import (
    Rows,
    WarehouseHarness,
    on_warehouse_cases,
    on_warehouses,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)

_ALL_SQL_WAREHOUSES: tuple[str, ...] = (
    "bigquery",
    "snowflake",
    "databricks",
    "postgres",
    "sqlserver",
)


@pytest.mark.parametrize("warehouse", on_warehouses(*_ALL_SQL_WAREHOUSES), indirect=True)
@pytest.mark.parametrize(
    "test_case",
    [
        NodeResultTestCase(
            description="direct node results persist and read",
            expected_rows=(
                ("check", "check_produce_result", "success"),
                ("task", "produce_result", "success"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_python_result_when_running_check_then_persists_node_results(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: NodeResultTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_node_results")
    project_name: str = f"{warehouse.name}_node_results"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": warehouse.project_toml(project_name, schema_name),
            "python/tasks/results.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def produce_result(ctx):\n"
                "    '''Test task produce_result.'''\n"
                "    return ctx.result(payload={'value': 42}, "
                f"metadata={{'source': '{warehouse.name}'}})\n"
            ),
            "python/checks/results.py": (
                "from sqlbuild.checks import check\n"
                "from python.tasks.results import produce_result\n\n"
                "@check(depends_on=produce_result)\n"
                "def check_produce_result(ctx):\n"
                "    '''Test check check_produce_result.'''\n    return ctx.result_of(node_function=produce_result).payload['value'] == 42\n"
            ),
        },
    )
    try:
        warehouse.ensure_schema(schema_name)
        build_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--select",
                "produce_result",
                "--exclude",
                "check:check_produce_result",
            ),
            project_dir=project_dir,
        )
        check_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "check", "--select", "check:check_produce_result"),
            project_dir=project_dir,
        )

        assert build_result.returncode == test_case.expected_return_code, (
            build_result.stdout + build_result.stderr
        )
        assert check_result.returncode == test_case.expected_return_code, (
            check_result.stdout + check_result.stderr
        )
        rows: Rows = warehouse.fetch_rows(
            schema_name,
            "SELECT node_type, node_name, status "
            f"FROM {warehouse.relation(schema_name, '_sqlbuild_node_results')} "
            "WHERE node_name IN ('produce_result', 'check_produce_result') "
            "ORDER BY node_type, node_name",
        )
        assert rows == test_case.expected_rows
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse", on_warehouses("bigquery", "snowflake", "databricks"), indirect=True
)
@pytest.mark.parametrize(
    "test_case",
    [
        CliTestCase(
            description="source freshness uses warehouse table metadata",
            command=("--no-color", "freshness", "--select", "raw_orders"),
            expected_stdout_fragments=(
                "Observed (1)",
                "raw_orders  value ",
                "kind timestamp",
                "via adapter",
                "OBSERVED=1  CHANGED=0  UNCHANGED=0  TOLERATED=0  UNKNOWN=0  ERROR=0",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_physical_source_without_freshness_when_running_then_uses_metadata(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: CliTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_freshness_meta")
    project_name: str = f"{warehouse.name}_freshness_metadata"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": warehouse.project_toml(project_name, schema_name),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n    description: Test source raw_orders.\n"
                f"{warehouse.source_location_yaml(schema_name)}"
                "    table: raw_orders\n"
            ),
            "models/orders.sql": (
                'MODEL (description "Test model orders.", materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    try:
        warehouse.ensure_schema(schema_name)
        warehouse.execute_sql(
            schema_name,
            f"CREATE OR REPLACE TABLE {warehouse.relation(schema_name, 'raw_orders')} "
            "AS SELECT 1 AS id",
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout, result.stdout
    finally:
        warehouse.cleanup_schema(schema_name)


_REPLAY_PASS_FRAGMENTS: tuple[str, ...] = (
    "transpilable_event_rollup",
    "PASS",
    "PASS=1  FAIL=0  ERROR=0  SKIP=0  TOTAL=1",
)
_REPLAY_X607_FRAGMENTS: tuple[str, ...] = (
    "local_transpile_error",
    "ERROR",
    "error[X607]",
    "PASS=0  FAIL=0  ERROR=1  SKIP=0  TOTAL=1",
)
_REPLAY_X608_FRAGMENTS: tuple[str, ...] = (
    "local_execution_error",
    "ERROR",
    "error[X608]",
    "PASS=0  FAIL=0  ERROR=1  SKIP=0  TOTAL=1",
)
_REPLAY_SCENARIO_HEADER: str = "SCENARIO (description 'Test scenario.');\n\nWITH\n"
_INTEGER_EVENTS_SCENARIO: str = (
    _REPLAY_SCENARIO_HEADER + "__source__raw_events AS (\n"
    "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
    "),\n"
    "__expected__event_rollup AS (\n"
    "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
    ")\n"
    "SELECT 1\n"
)


def _transpilable_replay_case(
    *,
    day: Callable[[str], str],
    large_amount: str,
    timestamp: Callable[[str], str],
    expected_day: str | None = None,
) -> ScenarioLocalReplayTestCase:
    """Build the passing local replay case from one dialect's day, filter and timestamp SQL."""

    return ScenarioLocalReplayTestCase(
        description="captures fixtures and replays transpilable SQL locally",
        model_sql=(
            "MODEL (description 'Test model.', materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            f"  {day('event_ts')} AS event_day,\n"
            f"  SUM({large_amount}) AS large_amount_cents,\n"
            "  COUNT(*) AS event_count\n"
            'FROM __source("raw_events")\n'
            f"GROUP BY customer_id, {day('event_ts')}\n"
        ),
        scenario_sql=(
            _REPLAY_SCENARIO_HEADER + "__source__raw_events AS (\n"
            f"  SELECT 10 AS customer_id, {timestamp('2026-01-01 08:15:00')} "
            "AS event_ts, 1500 AS amount_cents\n"
            "  UNION ALL\n"
            f"  SELECT 10 AS customer_id, {timestamp('2026-01-01 10:30:00')} "
            "AS event_ts, 500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id, "
            f"{expected_day or day(timestamp('2026-01-01 00:00:00'))} AS event_day, "
            "1500 AS large_amount_cents, 2 AS event_count\n"
            ")\n"
            "SELECT 1\n"
        ),
        expected_stdout_fragments=_REPLAY_PASS_FRAGMENTS,
        expected_local_rows=((10, 1500, 2),),
        local_rows_sql=(
            "SELECT customer_id, large_amount_cents, event_count "
            "FROM __sqb_local__model__event_rollup ORDER BY customer_id"
        ),
    )


_INTEGER_X607_CASE: ScenarioLocalReplayTestCase = ScenarioLocalReplayTestCase(
    description="reports local transpilation failures as X607",
    scenario_name="local_transpile_error",
    model_sql=(
        "MODEL (description 'Test model.', materialized table);\n\n"
        "SELECT customer_id, amount_cents\n"
        'FROM __source("raw_events")\n'
    ),
    scenario_sql=_INTEGER_EVENTS_SCENARIO,
    expected_stdout_fragments=_REPLAY_X607_FRAGMENTS,
    expected_return_code=1,
    corrupt_capture_dialect=True,
)
_INTEGER_X608_CASE: ScenarioLocalReplayTestCase = ScenarioLocalReplayTestCase(
    description="reports local DuckDB execution failures as X608",
    scenario_name="local_execution_error",
    model_sql=(
        "MODEL (description 'Test model.', materialized table);\n\n"
        "SELECT\n"
        "  customer_id,\n"
        "  __sqb_missing_local_function(amount_cents) AS amount_cents\n"
        'FROM __source("raw_events")\n'
    ),
    scenario_sql=_INTEGER_EVENTS_SCENARIO,
    expected_stdout_fragments=_REPLAY_X608_FRAGMENTS,
    expected_return_code=1,
)
_LARGE_AMOUNT_CASE: str = "CASE WHEN amount_cents >= 1000 THEN amount_cents ELSE 0 END"
_TEXT_EVENTS_SOURCE: str = "  SELECT 10 AS customer_id, '1500' AS amount_text\n"

_LOCAL_REPLAY_CASES: dict[str, tuple[ScenarioLocalReplayTestCase, ...]] = {
    "bigquery": (
        ScenarioLocalReplayTestCase(
            description="captures fixtures and replays transpilable SQL locally",
            model_sql=(
                "MODEL (description 'Test model.', materialized table);\n\n"
                "SELECT\n"
                "  customer_id,\n"
                "  TIMESTAMP_TRUNC(event_ts, DAY) AS event_day,\n"
                "  SUM(SAFE_CAST(amount_text AS INT64)) AS amount_cents,\n"
                "  COUNT(*) AS event_count\n"
                'FROM __source("raw_events")\n'
                "GROUP BY customer_id, TIMESTAMP_TRUNC(event_ts, DAY)\n"
            ),
            scenario_sql=(
                _REPLAY_SCENARIO_HEADER + "__source__raw_events AS (\n"
                "  SELECT 10 AS customer_id, TIMESTAMP '2026-01-01 08:15:00 UTC' "
                "AS event_ts, '1500' AS amount_text\n"
                "  UNION ALL\n"
                "  SELECT 10 AS customer_id, TIMESTAMP '2026-01-01 10:30:00 UTC' "
                "AS event_ts, '500' AS amount_text\n"
                "),\n"
                "__expected__event_rollup AS (\n"
                "  SELECT 10 AS customer_id, "
                "TIMESTAMP_TRUNC(TIMESTAMP '2026-01-01 00:00:00 UTC', DAY) AS event_day, "
                "2000 AS amount_cents, 2 AS event_count\n"
                ")\n"
                "SELECT 1\n"
            ),
            expected_stdout_fragments=_REPLAY_PASS_FRAGMENTS,
            expected_local_rows=((10, 2000, 2),),
            local_rows_sql=(
                "SELECT customer_id, amount_cents, event_count "
                "FROM __sqb_local__model__event_rollup ORDER BY customer_id"
            ),
        ),
        ScenarioLocalReplayTestCase(
            description="reports local transpilation failures as X607",
            scenario_name="local_transpile_error",
            model_sql=(
                "MODEL (description 'Test model.', materialized table);\n\n"
                "SELECT customer_id, SAFE_CAST(amount_text AS INT64) AS amount_cents\n"
                'FROM __source("raw_events")\n'
            ),
            scenario_sql=(
                _REPLAY_SCENARIO_HEADER + "__source__raw_events AS (\n"
                f"{_TEXT_EVENTS_SOURCE}"
                "),\n"
                "__expected__event_rollup AS (\n"
                f"{_TEXT_EVENTS_SOURCE}"
                ")\n"
                "SELECT 1\n"
            ),
            expected_stdout_fragments=_REPLAY_X607_FRAGMENTS,
            expected_return_code=1,
            corrupt_capture_dialect=True,
        ),
        ScenarioLocalReplayTestCase(
            description="reports local DuckDB execution failures as X608",
            scenario_name="local_execution_error",
            model_sql=(
                "MODEL (description 'Test model.', materialized table);\n\n"
                "SELECT\n"
                "  customer_id,\n"
                "  __sqb_missing_local_function(SAFE_CAST(amount_text AS INT64)) AS amount_cents\n"
                'FROM __source("raw_events")\n'
            ),
            scenario_sql=(
                _REPLAY_SCENARIO_HEADER + "__source__raw_events AS (\n"
                f"{_TEXT_EVENTS_SOURCE}"
                "),\n"
                "__expected__event_rollup AS (\n"
                "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
                ")\n"
                "SELECT 1\n"
            ),
            expected_stdout_fragments=_REPLAY_X608_FRAGMENTS,
            expected_return_code=1,
        ),
    ),
    "snowflake": (
        _transpilable_replay_case(
            day=lambda value: f"DATE_TRUNC('DAY', {value})",
            large_amount="IFF(amount_cents >= 1000, amount_cents, 0)",
            timestamp=lambda value: f"TO_TIMESTAMP_NTZ('{value}')",
        ),
        _INTEGER_X607_CASE,
        _INTEGER_X608_CASE,
    ),
    "databricks": (
        _transpilable_replay_case(
            day=lambda value: f"date_trunc('DAY', {value})",
            large_amount="if(amount_cents >= 1000, amount_cents, 0)",
            timestamp=lambda value: f"TIMESTAMP '{value}'",
        ),
        _INTEGER_X607_CASE,
        _INTEGER_X608_CASE,
    ),
    "postgres": (
        _transpilable_replay_case(
            day=lambda value: f"DATE_TRUNC('day', {value})",
            large_amount=_LARGE_AMOUNT_CASE,
            timestamp=lambda value: f"CAST('{value}' AS TIMESTAMP)",
        ),
        _INTEGER_X607_CASE,
    ),
    "sqlserver": (
        _transpilable_replay_case(
            day=lambda value: f"CAST(CAST({value} AS DATE) AS DATETIME2)",
            large_amount=_LARGE_AMOUNT_CASE,
            timestamp=lambda value: f"CAST('{value}' AS DATETIME2)",
            expected_day="CAST(CAST('2026-01-01 00:00:00' AS DATE) AS DATETIME2)",
        ),
        _INTEGER_X607_CASE,
    ),
}


@pytest.mark.parametrize(
    "warehouse, test_case", on_warehouse_cases(_LOCAL_REPLAY_CASES), indirect=["warehouse"]
)
def test_given_scenario_capture_when_replaying_locally_then_transpilable_sql_passes(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: ScenarioLocalReplayTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_scenario_local")
    project_name: str = f"{warehouse.name}_scenario_local_replay"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files=build_real_warehouse_local_replay_project_files(
            project_toml=warehouse.project_toml(project_name, schema_name),
            model_sql=test_case.model_sql,
            scenario_sql=test_case.scenario_sql,
            scenario_name=test_case.scenario_name,
        ),
    )
    warehouse.ensure_schema(schema_name)

    try:
        capture_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "capture", test_case.scenario_name),
            project_dir=project_dir,
        )
        assert capture_result.returncode == 0, capture_result.stdout + capture_result.stderr
        maybe_corrupt_scenario_snapshot_dialect(
            project_dir=project_dir,
            scenario_name=test_case.scenario_name,
            enabled=test_case.corrupt_capture_dialect,
        )

        replay_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test", test_case.scenario_name, "--local"),
            project_dir=project_dir,
        )

        assert replay_result.returncode == test_case.expected_return_code, (
            replay_result.stdout + replay_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in replay_result.stdout
        assert_optional_local_replay_rows(
            project_dir=project_dir,
            scenario_name=test_case.scenario_name,
            local_rows_sql=test_case.local_rows_sql,
            expected_local_rows=test_case.expected_local_rows,
        )
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse", on_warehouses("bigquery", "snowflake", "databricks"), indirect=True
)
@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioRemoteTestCase(
            description="runs scenario remotely and retains inspectable artifacts",
            expected_stdout_fragments=(
                "remote_event_rollup",
                "Retained relations:",
                "source raw_events -> __sqb_",
                "model  stg_events -> __sqb_",
                "model  event_rollup -> __sqb_",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_retained_suffix_counts={
                "__source__raw_events": 1,
                "__model__stg_events": 1,
                "__model__event_rollup": 1,
            },
            expected_row_counts_by_suffix={
                "__source__raw_events": 2,
                "__model__stg_events": 1,
                "__model__event_rollup": 1,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_when_running_remotely_then_cleans_up_and_retains_artifacts(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: ScenarioRemoteTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_scenario_remote")
    project_name: str = f"{warehouse.name}_scenario_remote"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files=build_real_warehouse_remote_scenario_project_files(
            project_toml=warehouse.project_toml(project_name, schema_name),
        ),
    )
    warehouse.ensure_schema(schema_name)

    try:
        cleanup_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test", "remote_event_rollup"),
            project_dir=project_dir,
        )
        assert cleanup_result.returncode == 0, cleanup_result.stdout + cleanup_result.stderr
        assert warehouse.scenario_relation_names(schema_name) == ()

        retain_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test", "remote_event_rollup", "--retain"),
            project_dir=project_dir,
        )

        assert retain_result.returncode == 0, retain_result.stdout + retain_result.stderr
        for expected_fragment in test_case.expected_stdout_fragments:
            assert expected_fragment in retain_result.stdout
        retained_names: tuple[str, ...] = warehouse.scenario_relation_names(schema_name)
        assert len(retained_names) == sum(test_case.expected_retained_suffix_counts.values())
        retained_names_by_suffix: defaultdict[str, list[str]] = defaultdict(list)
        for relation in retained_names:
            retained_names_by_suffix[relation[relation.index("__", 2) :]].append(relation)
        for suffix, expected_count in test_case.expected_retained_suffix_counts.items():
            assert len(retained_names_by_suffix[suffix]) == expected_count
        for suffix, expected_count in test_case.expected_row_counts_by_suffix.items():
            matches: tuple[str, ...] = tuple(retained_names_by_suffix[suffix])
            assert len(matches) == 1
            assert warehouse.row_count(schema_name, matches[0]) == expected_count
    finally:
        warehouse.cleanup_schema(schema_name)
