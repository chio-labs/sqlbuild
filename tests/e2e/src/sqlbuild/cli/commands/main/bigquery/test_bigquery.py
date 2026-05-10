from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.bigquery._test_types import (
    BigQueryBuildE2ETestCase,
    BigQueryCliTestCase,
    BigQueryDiffE2ETestCase,
    BigQueryErrorE2ETestCase,
    BigQueryModelBuildE2ETestCase,
    BigQueryScenarioLocalReplayE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.bigquery.helpers import (
    build_bigquery_project_toml,
    cleanup_bigquery_dataset,
    ensure_bigquery_dataset_ready,
    execute_bigquery_sql,
    fetch_bigquery_rows,
    prepare_bigquery_diff_project,
    prepare_bigquery_query_source,
    prepare_bigquery_waffle_shop,
    relation_name,
    write_local_environment_override,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    assert_optional_local_replay_rows,
    build_real_warehouse_local_replay_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)
from tests.integration.src.sqlbuild.integrations.bigquery.helpers import build_unique_dataset_name

BIGQUERY_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES: list[BigQueryScenarioLocalReplayE2ETestCase] = [
    BigQueryScenarioLocalReplayE2ETestCase(
        description="captures bigquery fixtures and replays transpilable SQL locally",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  TIMESTAMP_TRUNC(event_ts, DAY) AS event_day,\n"
            "  SUM(SAFE_CAST(amount_text AS INT64)) AS amount_cents,\n"
            "  COUNT(*) AS event_count\n"
            'FROM __source("raw_events")\n'
            "GROUP BY customer_id, TIMESTAMP_TRUNC(event_ts, DAY)\n"
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
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
        expected_stdout_fragments=(
            "transpilable_event_rollup",
            "PASS",
            "PASS=1  FAIL=0  ERROR=0  SKIP=0  TOTAL=1",
        ),
        expected_local_rows=((10, 2000, 2),),
        local_rows_sql=(
            "SELECT customer_id, amount_cents, event_count "
            "FROM __sqb_local__model__event_rollup ORDER BY customer_id"
        ),
    ),
    BigQueryScenarioLocalReplayE2ETestCase(
        description="reports bigquery local transpilation failures as X607",
        scenario_name="local_transpile_error",
        model_sql=(
            'MODEL (materialized table);\n\nSELECT *\nFROM __source("raw_events")\nQUALIFY\n'
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, '1500' AS amount_text\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id, '1500' AS amount_text\n"
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
    ),
    BigQueryScenarioLocalReplayE2ETestCase(
        description="reports bigquery local DuckDB execution failures as X608",
        scenario_name="local_execution_error",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  __sqb_missing_local_function(SAFE_CAST(amount_text AS INT64)) AS amount_cents\n"
            'FROM __source("raw_events")\n'
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, '1500' AS amount_text\n"
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

BIGQUERY_QUERY_E2E_TEST_CASES: list[BigQueryCliTestCase] = [
    BigQueryCliTestCase(
        description="query command uses bigquery local override",
        command=("query", "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID"),
        expected_stdout_fragments=("ID   | 1", "NAME | alice", "ID   | 2", "NAME | bob"),
    ),
    BigQueryCliTestCase(
        description="query command renders json output",
        command=(
            "query",
            "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID LIMIT 1",
            "--format",
            "json",
        ),
        expected_stdout_fragments=('"ID": 1', '"NAME": "alice"'),
    ),
    BigQueryCliTestCase(
        description="query command renders csv output",
        command=(
            "query",
            "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID LIMIT 1",
            "--format",
            "csv",
        ),
        expected_stdout_fragments=("ID,NAME", "1,alice"),
    ),
    BigQueryCliTestCase(
        description="query command prints ok for ddl statements",
        command=("query", "CREATE OR REPLACE TABLE {ddl_target} (id INT64)"),
        expected_stdout_fragments=("OK",),
    ),
]

BIGQUERY_MODEL_BUILD_E2E_TEST_CASES: list[BigQueryModelBuildE2ETestCase] = [
    BigQueryModelBuildE2ETestCase(
        description="hourly_order_activity uses timestamp_trunc",
        model_name="hourly_order_activity",
        expected_sql_fragment="TIMESTAMP_TRUNC(",
    ),
    BigQueryModelBuildE2ETestCase(
        description="daily_activity_rollup uses timestamp_trunc",
        model_name="daily_activity_rollup",
        expected_sql_fragment="TIMESTAMP_TRUNC(",
    ),
    BigQueryModelBuildE2ETestCase(
        description="hourly_activity_with_daily_context uses timestamp_trunc",
        model_name="hourly_activity_with_daily_context",
        expected_sql_fragment="TIMESTAMP_TRUNC(",
    ),
    BigQueryModelBuildE2ETestCase(
        description="order_status_index uses qualified refs",
        model_name="order_status_index",
        expected_sql_fragment="`",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_QUERY_E2E_TEST_CASES,
    ids=[case.description for case in BIGQUERY_QUERY_E2E_TEST_CASES],
)
def test_given_bigquery_local_config_when_running_query_then_outputs_expected_rows(
    tmp_path: Path,
    test_case: BigQueryCliTestCase,
) -> None:
    project_dir: Path
    dataset_name: str
    project_dir, dataset_name = prepare_bigquery_waffle_shop(tmp_path=tmp_path)
    ensure_bigquery_dataset_ready(dataset_name=dataset_name)
    source_name: str = prepare_bigquery_query_source(dataset_name=dataset_name)
    ddl_target: str = relation_name(dataset_name=dataset_name, name="query_target")
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
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES,
    ids=[case.description for case in BIGQUERY_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES],
)
def test_given_bigquery_scenario_capture_when_replaying_locally_then_transpilable_sql_passes(
    tmp_path: Path,
    test_case: BigQueryScenarioLocalReplayE2ETestCase,
) -> None:
    dataset_name: str = build_unique_dataset_name(prefix="sqlbuild_scenario_local")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="bigquery_scenario_local_replay",
        repo_files=build_real_warehouse_local_replay_project_files(
            project_toml=build_bigquery_project_toml(
                project_name="bigquery_scenario_local_replay",
                dataset_name=dataset_name,
            ),
            model_sql=test_case.model_sql,
            scenario_sql=test_case.scenario_sql,
            scenario_name=test_case.scenario_name,
        ),
    )
    ensure_bigquery_dataset_ready(dataset_name=dataset_name)

    try:
        capture_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "scenario",
                "capture",
                "--no-sql-validation",
                test_case.scenario_name,
            ),
            project_dir=project_dir,
        )
        assert capture_result.returncode == 0, capture_result.stdout + capture_result.stderr

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
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryBuildE2ETestCase(
            description="waffle shop full build succeeds on bigquery",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_fact_order_rows=(
                (1, "Classic Belgian", "sweet", 1700, "completed", "success"),
                (3, "Chicken and Waffle", "savory", 4350, "completed", "success"),
                (10, "Classic Belgian", "sweet", 3400, "placed", None),
            ),
            expected_udf_rows=((1, True), (10, False)),
            expected_python_udf_rows=((1, True), (10, False)),
            expected_daily_revenue_rows=(
                ("2026-04-01", 3, 6, 7100),
                ("2026-04-02", 3, 3, 2550),
                ("2026-04-03", 1, 1, 950),
            ),
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["waffle shop full build succeeds on bigquery"],
)
def test_given_waffle_shop_when_running_full_build_on_bigquery_then_expected_table_exists(
    tmp_path: Path,
    test_case: BigQueryBuildE2ETestCase,
) -> None:
    project_dir: Path
    dataset_name: str
    project_dir, dataset_name = prepare_bigquery_waffle_shop(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dataset_name,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(dataset_name=dataset_name, name=test_case.expected_table_name)}"
            ),
        )
        row_count: object = rows[0][0]
        assert isinstance(row_count, int)
        assert row_count == test_case.expected_row_count
        fact_order_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dataset_name,
            sql=(
                "SELECT order_id, waffle_name, waffle_category, line_total_cents, "
                "order_status, payment_status FROM "
                f"{relation_name(dataset_name=dataset_name, name='fact_orders')} "
                "WHERE order_id IN (1, 3, 10) ORDER BY order_id"
            ),
        )
        assert fact_order_rows == test_case.expected_fact_order_rows
        udf_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dataset_name,
            sql=(
                "SELECT order_id, is_completed_order FROM "
                f"{relation_name(dataset_name=dataset_name, name='fact_orders')} "
                "WHERE order_id IN (1, 10) ORDER BY order_id"
            ),
        )
        assert udf_rows == test_case.expected_udf_rows
        python_udf_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dataset_name,
            sql=(
                "SELECT order_id, is_completed_order_py FROM "
                f"{relation_name(dataset_name=dataset_name, name='fact_orders')} "
                "WHERE order_id IN (1, 10) ORDER BY order_id"
            ),
        )
        assert python_udf_rows == test_case.expected_python_udf_rows
        daily_revenue_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dataset_name,
            sql=(
                "SELECT CAST(revenue_date AS STRING), order_count, waffles_sold, "
                "total_revenue_cents FROM "
                f"{relation_name(dataset_name=dataset_name, name='daily_revenue')} "
                "ORDER BY revenue_date"
            ),
        )
        assert daily_revenue_rows == test_case.expected_daily_revenue_rows
        run_dir: Path = project_dir / "target" / "run" / "models"
        hourly_sql: str = (run_dir / "marts" / "hourly_order_activity.sql").read_text(
            encoding="utf-8"
        )
        daily_sql: str = (run_dir / "marts" / "daily_activity_rollup.sql").read_text(
            encoding="utf-8"
        )
        contextual_sql: str = (
            run_dir / "marts" / "hourly_activity_with_daily_context.sql"
        ).read_text(encoding="utf-8")
        order_status_sql: str = (run_dir / "intermediate" / "order_status_index.sql").read_text(
            encoding="utf-8"
        )
        log_sql: str = (project_dir / "target" / "sqlbuild.log").read_text(encoding="utf-8")
        fact_orders_relation: str = relation_name(dataset_name=dataset_name, name="fact_orders")
        project_prefix: str = fact_orders_relation.removesuffix(".fact_orders`")
        assert "TIMESTAMP_TRUNC(" in hourly_sql
        assert "TIMESTAMP_TRUNC(" in daily_sql
        assert "TIMESTAMP_TRUNC(" in contextual_sql
        assert "`" in order_status_sql
        assert project_prefix in log_sql
        assert f"{project_prefix}._sqlbuild_fingerprints`" in log_sql
        assert "__delta`" in log_sql
        assert "TIMESTAMP '" in log_sql
    finally:
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_MODEL_BUILD_E2E_TEST_CASES,
    ids=[case.description for case in BIGQUERY_MODEL_BUILD_E2E_TEST_CASES],
)
def test_given_bigquery_waffle_shop_model_when_building_then_portable_sql_succeeds(
    tmp_path: Path,
    test_case: BigQueryModelBuildE2ETestCase,
) -> None:
    project_dir: Path
    dataset_name: str
    project_dir, dataset_name = prepare_bigquery_waffle_shop(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        compiled_files: tuple[Path, ...] = tuple(
            (project_dir / "target" / "run" / "models").glob(f"**/{test_case.model_name}.sql")
        )
        assert len(compiled_files) == 1
        assert test_case.expected_sql_fragment in compiled_files[0].read_text(encoding="utf-8")
    finally:
        cleanup_bigquery_dataset(dataset_name=dataset_name)


BIGQUERY_DIFF_E2E_TEST_CASES: list[BigQueryDiffE2ETestCase] = [
    BigQueryDiffE2ETestCase(
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
    BigQueryDiffE2ETestCase(
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
    BigQueryDiffE2ETestCase(
        description="verbose diff shows changed row examples",
        mutation_sql=("UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 1",),
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--verbose",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("Examples", "order_id=1 | 100 -> 105"),
        expected_return_code=1,
    ),
    BigQueryDiffE2ETestCase(
        description="verbose diff shows side only examples",
        mutation_sql=(
            "DELETE FROM stg_orders WHERE order_id = 1",
            "INSERT INTO stg_orders (order_id, customer_id, amount_cents) VALUES (3, 3, 999)",
        ),
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--full",
            "--verbose",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("prod only", "order_id=1", "dev only", "order_id=3"),
        expected_return_code=1,
    ),
    BigQueryDiffE2ETestCase(
        description="bounded diff reports mismatch inside bounded window",
        mutation_sql=("UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 2",),
        command=(
            "--no-color",
            "diff",
            "prod:dev",
            "--bounded",
            "2",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("amount_cents", "mismatches=1", "order_id=2 | 200 -> 205"),
        expected_return_code=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryErrorE2ETestCase(
            description="query preserves underlying error",
            command=("query", "SELECT missing_column FROM UNNEST([STRUCT(1 AS id)])"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=["query preserves underlying error"],
)
def test_given_bigquery_invalid_query_when_running_query_then_underlying_error_is_preserved(
    tmp_path: Path,
    test_case: BigQueryErrorE2ETestCase,
) -> None:
    project_dir: Path
    dataset_name: str
    project_dir, dataset_name = prepare_bigquery_waffle_shop(tmp_path=tmp_path)
    ensure_bigquery_dataset_ready(dataset_name=dataset_name)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code
        assert test_case.expected_error_fragment in result.stdout + result.stderr
    finally:
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryErrorE2ETestCase(
            description="build preserves underlying error",
            command=("--no-color", "build", "--select", "bigquery_broken_model"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=["build preserves underlying error"],
)
def test_given_bigquery_invalid_model_when_building_then_underlying_error_is_preserved(
    tmp_path: Path,
    test_case: BigQueryErrorE2ETestCase,
) -> None:
    project_dir: Path
    dataset_name: str
    project_dir, dataset_name = prepare_bigquery_waffle_shop(tmp_path=tmp_path)
    broken_model: Path = project_dir / "models" / "marts" / "bigquery_broken_model.sql"
    broken_model.write_text(
        "MODEL (materialized table);\n\nSELECT missing_column FROM UNNEST([STRUCT(1 AS id)])",
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
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_DIFF_E2E_TEST_CASES,
    ids=[case.description for case in BIGQUERY_DIFF_E2E_TEST_CASES],
)
def test_given_bigquery_project_when_running_diff_then_outputs_expected_summary(
    tmp_path: Path,
    test_case: BigQueryDiffE2ETestCase,
) -> None:
    project_dir: Path
    prod_dataset: str
    dev_dataset: str
    project_dir, prod_dataset, dev_dataset = prepare_bigquery_diff_project(tmp_path=tmp_path)

    try:
        write_local_environment_override(project_dir=project_dir, environment="prod")
        prod_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert prod_build.returncode == 0, prod_build.stdout + prod_build.stderr

        write_local_environment_override(project_dir=project_dir, environment="dev")
        dev_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert dev_build.returncode == 0, dev_build.stdout + dev_build.stderr

        statement: str
        for statement in test_case.mutation_sql:
            execute_bigquery_sql(
                dataset_name=dev_dataset,
                sql=statement.replace(
                    "stg_orders",
                    relation_name(dataset_name=dev_dataset, name="stg_orders"),
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
        cleanup_bigquery_dataset(dataset_name=prod_dataset)
        cleanup_bigquery_dataset(dataset_name=dev_dataset)
