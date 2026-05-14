from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.databricks._test_types import (
    DatabricksBuildE2ETestCase,
    DatabricksCliTestCase,
    DatabricksCloneE2ETestCase,
    DatabricksDiffE2ETestCase,
    DatabricksErrorE2ETestCase,
    DatabricksScenarioLocalReplayE2ETestCase,
    DatabricksScenarioRemoteE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.databricks.helpers import (
    build_databricks_project_toml,
    cleanup_databricks_schema,
    databricks_relation_row_count,
    ensure_databricks_schema_ready,
    execute_databricks_sql,
    fetch_databricks_rows,
    list_databricks_scenario_relation_names,
    prepare_databricks_diff_project,
    prepare_databricks_query_source,
    prepare_databricks_waffle_shop,
    relation_name,
    write_local_environment_override,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    assert_optional_local_replay_rows,
    build_real_warehouse_local_replay_project_files,
    build_real_warehouse_remote_scenario_project_files,
    maybe_corrupt_scenario_snapshot_dialect,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)
from tests.integration.src.sqlbuild.integrations.databricks.helpers import build_unique_schema_name

DATABRICKS_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES: list[DatabricksScenarioLocalReplayE2ETestCase] = [
    DatabricksScenarioLocalReplayE2ETestCase(
        description="captures databricks fixtures and replays transpilable SQL locally",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  date_trunc('DAY', event_ts) AS event_day,\n"
            "  SUM(if(amount_cents >= 1000, amount_cents, 0)) AS large_amount_cents,\n"
            "  COUNT(*) AS event_count\n"
            'FROM __source("raw_events")\n'
            "GROUP BY customer_id, date_trunc('DAY', event_ts)\n"
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, TIMESTAMP '2026-01-01 08:15:00' "
            "AS event_ts, 1500 AS amount_cents\n"
            "  UNION ALL\n"
            "  SELECT 10 AS customer_id, TIMESTAMP '2026-01-01 10:30:00' "
            "AS event_ts, 500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id, "
            "date_trunc('DAY', TIMESTAMP '2026-01-01 00:00:00') AS event_day, "
            "1500 AS large_amount_cents, 2 AS event_count\n"
            ")\n"
            "SELECT 1\n"
        ),
        expected_stdout_fragments=(
            "transpilable_event_rollup",
            "PASS",
            "PASS=1  FAIL=0  ERROR=0  SKIP=0  TOTAL=1",
        ),
        expected_local_rows=((10, 1500, 2),),
        local_rows_sql=(
            "SELECT customer_id, large_amount_cents, event_count "
            "FROM __sqb_local__model__event_rollup ORDER BY customer_id"
        ),
    ),
    DatabricksScenarioLocalReplayE2ETestCase(
        description="reports databricks local transpilation failures as X607",
        scenario_name="local_transpile_error",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT customer_id, amount_cents\n"
            'FROM __source("raw_events")\n'
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
            ")\n"
            "SELECT 1\n"
        ),
        expected_stdout_fragments=(
            "local_transpile_error",
            "ERROR",
            "error[X607]",
            "PASS=0  FAIL=0  ERROR=1  SKIP=0  TOTAL=1",
        ),
        expected_return_code=1,
        corrupt_capture_dialect=True,
    ),
    DatabricksScenarioLocalReplayE2ETestCase(
        description="reports databricks local DuckDB execution failures as X608",
        scenario_name="local_execution_error",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  __sqb_missing_local_function(amount_cents) AS amount_cents\n"
            'FROM __source("raw_events")\n'
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id, 1500 AS amount_cents\n"
            ")\n"
            "SELECT 1\n"
        ),
        expected_stdout_fragments=(
            "local_execution_error",
            "ERROR",
            "error[X608]",
            "PASS=0  FAIL=0  ERROR=1  SKIP=0  TOTAL=1",
        ),
        expected_return_code=1,
    ),
]

DATABRICKS_QUERY_E2E_TEST_CASES: list[DatabricksCliTestCase] = [
    DatabricksCliTestCase(
        description="query command uses databricks local override",
        command=("query", "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID"),
        expected_stdout_fragments=("ID   | 1", "NAME | alice", "ID   | 2", "NAME | bob"),
    ),
    DatabricksCliTestCase(
        description="query command renders json output",
        command=(
            "query",
            "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID LIMIT 1",
            "--format",
            "json",
        ),
        expected_stdout_fragments=('"ID": 1', '"NAME": "alice"'),
    ),
    DatabricksCliTestCase(
        description="query command renders csv output",
        command=(
            "query",
            "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID LIMIT 1",
            "--format",
            "csv",
        ),
        expected_stdout_fragments=("ID,NAME", "1,alice"),
    ),
    DatabricksCliTestCase(
        description="query command prints ok for ddl statements",
        command=("query", "CREATE OR REPLACE TABLE {ddl_target} (id INT)"),
        expected_stdout_fragments=("OK",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_QUERY_E2E_TEST_CASES,
    ids=[case.description for case in DATABRICKS_QUERY_E2E_TEST_CASES],
)
def test_given_databricks_local_config_when_running_query_then_outputs_expected_rows(
    tmp_path: Path,
    test_case: DatabricksCliTestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)
    ensure_databricks_schema_ready(schema_name=schema_name)
    source_name: str = prepare_databricks_query_source(schema_name=schema_name)
    ddl_target: str = relation_name(schema_name=schema_name, name="query_target")
    command: tuple[str, ...] = tuple(
        part.format(source=source_name, ddl_target=ddl_target) for part in test_case.command
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(command=command, project_dir=project_dir)

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES,
    ids=[case.description for case in DATABRICKS_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES],
)
def test_given_databricks_scenario_capture_when_replaying_locally_then_transpilable_sql_passes(
    tmp_path: Path,
    test_case: DatabricksScenarioLocalReplayE2ETestCase,
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_scenario_local")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="databricks_scenario_local_replay",
        repo_files=build_real_warehouse_local_replay_project_files(
            project_toml=build_databricks_project_toml(
                project_name="databricks_scenario_local_replay",
                schema_name=schema_name,
            ),
            model_sql=test_case.model_sql,
            scenario_sql=test_case.scenario_sql,
            scenario_name=test_case.scenario_name,
        ),
    )
    ensure_databricks_schema_ready(schema_name=schema_name)

    try:
        capture_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "scenario",
                "capture",
                test_case.scenario_name,
            ),
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
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in replay_result.stdout
        assert_optional_local_replay_rows(
            project_dir=project_dir,
            scenario_name=test_case.scenario_name,
            local_rows_sql=test_case.local_rows_sql,
            expected_local_rows=test_case.expected_local_rows,
        )
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksScenarioRemoteE2ETestCase(
            description="runs databricks scenario remotely and retains inspectable artifacts",
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
    ids=["runs databricks scenario remotely and retains inspectable artifacts"],
)
def test_given_databricks_scenario_when_running_remotely_then_cleans_up_and_retains_artifacts(
    tmp_path: Path,
    test_case: DatabricksScenarioRemoteE2ETestCase,
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_scenario_remote")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="databricks_scenario_remote",
        repo_files=build_real_warehouse_remote_scenario_project_files(
            project_toml=build_databricks_project_toml(
                project_name="databricks_scenario_remote",
                schema_name=schema_name,
            ),
        ),
    )
    ensure_databricks_schema_ready(schema_name=schema_name)

    try:
        cleanup_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test", "remote_event_rollup"),
            project_dir=project_dir,
        )
        assert cleanup_result.returncode == 0, cleanup_result.stdout + cleanup_result.stderr
        assert list_databricks_scenario_relation_names(schema_name=schema_name) == ()

        retain_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test", "remote_event_rollup", "--retain"),
            project_dir=project_dir,
        )

        assert retain_result.returncode == 0, retain_result.stdout + retain_result.stderr
        expected_fragment: str
        for expected_fragment in test_case.expected_stdout_fragments:
            assert expected_fragment in retain_result.stdout
        retained_names: tuple[str, ...] = list_databricks_scenario_relation_names(
            schema_name=schema_name
        )
        assert len(retained_names) == sum(test_case.expected_retained_suffix_counts.values())
        suffix: str
        for suffix, expected_count in test_case.expected_retained_suffix_counts.items():
            matches: tuple[str, ...] = tuple(
                relation for relation in retained_names if relation.endswith(suffix)
            )
            assert len(matches) == expected_count
        for suffix, expected_count in test_case.expected_row_counts_by_suffix.items():
            matches = tuple(relation for relation in retained_names if relation.endswith(suffix))
            assert len(matches) == 1
            assert (
                databricks_relation_row_count(schema_name=schema_name, relation=matches[0])
                == expected_count
            )
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksBuildE2ETestCase(
            description="waffle shop full build succeeds on databricks",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_fact_order_rows=(
                (1, "Classic Belgian", "sweet", 1700, "completed", "success"),
                (3, "Chicken and Waffle", "savory", 4350, "completed", "success"),
                (10, "Classic Belgian", "sweet", 3400, "placed", None),
            ),
            expected_udf_rows=((1, True, True), (10, False, False)),
            expected_daily_revenue_rows=(
                ("2026-04-01", 3, 6, 7100),
                ("2026-04-02", 3, 3, 2550),
                ("2026-04-03", 1, 1, 950),
            ),
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["waffle shop full build succeeds on databricks"],
)
def test_given_waffle_shop_when_running_full_build_on_databricks_then_expected_values_exist(
    tmp_path: Path,
    test_case: DatabricksBuildE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
        )
        assert rows[0][0] == test_case.expected_row_count
        fact_order_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT order_id, waffle_name, waffle_category, line_total_cents, "
                "order_status, payment_status FROM "
                f"{relation_name(schema_name=schema_name, name='fact_orders')} "
                "WHERE order_id IN (1, 3, 10) ORDER BY order_id"
            ),
        )
        assert fact_order_rows == test_case.expected_fact_order_rows
        udf_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT order_id, is_completed_order, is_completed_order_py FROM "
                f"{relation_name(schema_name=schema_name, name='fact_orders')} "
                "WHERE order_id IN (1, 10) ORDER BY order_id"
            ),
        )
        assert udf_rows == test_case.expected_udf_rows
        daily_revenue_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT CAST(revenue_date AS STRING), order_count, waffles_sold, "
                "total_revenue_cents FROM "
                f"{relation_name(schema_name=schema_name, name='daily_revenue')} "
                "ORDER BY revenue_date"
            ),
        )
        assert daily_revenue_rows == test_case.expected_daily_revenue_rows
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


DATABRICKS_DIFF_E2E_TEST_CASES: list[DatabricksDiffE2ETestCase] = [
    DatabricksDiffE2ETestCase(
        description="schema only diff reports clean identical schemas",
        mutation_sql=(),
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--schema-only",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("stg_orders", "No schema differences."),
        expected_return_code=0,
    ),
    DatabricksDiffE2ETestCase(
        description="full diff reports row mismatch",
        mutation_sql=("UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 1",),
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("amount_cents", "mismatches=1", "order_id=1 | 100 -> 105"),
        expected_return_code=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_DIFF_E2E_TEST_CASES,
    ids=[case.description for case in DATABRICKS_DIFF_E2E_TEST_CASES],
)
def test_given_databricks_project_when_running_diff_then_outputs_expected_summary(
    tmp_path: Path,
    test_case: DatabricksDiffE2ETestCase,
) -> None:
    project_dir: Path
    prod_schema: str
    dev_schema: str
    project_dir, prod_schema, dev_schema = prepare_databricks_diff_project(tmp_path=tmp_path)

    try:
        write_local_environment_override(
            project_dir=project_dir,
            environment="prod",
            schema_name=prod_schema,
        )
        prod_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert prod_build.returncode == 0, prod_build.stdout + prod_build.stderr

        write_local_environment_override(
            project_dir=project_dir,
            environment="dev",
            schema_name=dev_schema,
        )
        dev_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert dev_build.returncode == 0, dev_build.stdout + dev_build.stderr

        statement: str
        for statement in test_case.mutation_sql:
            execute_databricks_sql(
                schema_name=dev_schema,
                sql=statement.replace(
                    "stg_orders",
                    relation_name(schema_name=dev_schema, name="stg_orders"),
                ),
            )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
    finally:
        cleanup_databricks_schema(schema_name=prod_schema)
        cleanup_databricks_schema(schema_name=dev_schema)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksCloneE2ETestCase(
            description="clone defaults to shallow clone and hard copy uses CTAS",
            default_command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "stg_orders",
            ),
            hard_copy_command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--hard-copy",
                "--select",
                "stg_orders",
            ),
            expected_default_stdout_fragments=(
                "stg_orders",
                "cloned",
                "CLONED=1  COPIED=0",
                "PASS=1  WARN=0  FAIL=0  TOTAL=1",
            ),
            expected_hard_copy_stdout_fragments=(
                "stg_orders",
                "copied",
                "CLONED=0  COPIED=1",
                "PASS=1  WARN=0  FAIL=0  TOTAL=1",
            ),
            expected_rows=((1, 1, 100), (2, 2, 200)),
        )
    ],
    ids=["clone defaults to shallow clone and hard copy uses CTAS"],
)
def test_given_databricks_project_when_cloning_then_default_uses_shallow_clone_and_hard_copy_ctas(
    tmp_path: Path,
    test_case: DatabricksCloneE2ETestCase,
) -> None:
    project_dir: Path
    prod_schema: str
    dev_schema: str
    project_dir, prod_schema, dev_schema = prepare_databricks_diff_project(tmp_path=tmp_path)

    try:
        write_local_environment_override(
            project_dir=project_dir,
            environment="prod",
            schema_name=prod_schema,
        )
        prod_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert prod_build.returncode == 0, prod_build.stdout + prod_build.stderr
        ensure_databricks_schema_ready(schema_name=dev_schema)

        default_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.default_command,
            project_dir=project_dir,
        )
        assert default_result.returncode == 0, default_result.stdout + default_result.stderr
        fragment: str
        for fragment in test_case.expected_default_stdout_fragments:
            assert fragment in default_result.stdout
        cloned_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=dev_schema,
            sql=(
                "SELECT order_id, customer_id, amount_cents FROM "
                f"{relation_name(schema_name=dev_schema, name='stg_orders')} ORDER BY order_id"
            ),
        )
        assert cloned_rows == test_case.expected_rows

        execute_databricks_sql(
            schema_name=dev_schema,
            sql=f"DROP TABLE {relation_name(schema_name=dev_schema, name='stg_orders')}",
        )
        hard_copy_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.hard_copy_command,
            project_dir=project_dir,
        )
        assert hard_copy_result.returncode == 0, hard_copy_result.stdout + hard_copy_result.stderr
        for fragment in test_case.expected_hard_copy_stdout_fragments:
            assert fragment in hard_copy_result.stdout
        copied_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=dev_schema,
            sql=(
                "SELECT order_id, customer_id, amount_cents FROM "
                f"{relation_name(schema_name=dev_schema, name='stg_orders')} ORDER BY order_id"
            ),
        )
        assert copied_rows == test_case.expected_rows
    finally:
        cleanup_databricks_schema(schema_name=prod_schema)
        cleanup_databricks_schema(schema_name=dev_schema)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksErrorE2ETestCase(
            description="query preserves underlying error",
            command=("query", "SELECT missing_column FROM (SELECT 1 AS id)"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=["query preserves underlying error"],
)
def test_given_databricks_invalid_query_when_running_query_then_underlying_error_is_preserved(
    tmp_path: Path,
    test_case: DatabricksErrorE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)
    ensure_databricks_schema_ready(schema_name=schema_name)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code
        assert test_case.expected_error_fragment in result.stdout + result.stderr
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksErrorE2ETestCase(
            description="build preserves underlying error",
            command=("--no-color", "build", "--select", "databricks_broken_model"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=["build preserves underlying error"],
)
def test_given_databricks_invalid_model_when_building_then_underlying_error_is_preserved(
    tmp_path: Path,
    test_case: DatabricksErrorE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)
    broken_model: Path = project_dir / "models" / "marts" / "databricks_broken_model.sql"
    broken_model.write_text(
        "MODEL (materialized table);\n\nSELECT missing_column FROM (SELECT 1 AS id)",
        encoding="utf-8",
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code
        assert test_case.expected_error_fragment in result.stdout + result.stderr
    finally:
        cleanup_databricks_schema(schema_name=schema_name)
