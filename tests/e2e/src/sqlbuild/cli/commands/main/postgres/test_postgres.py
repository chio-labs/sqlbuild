from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresBuildE2ETestCase,
    PostgresScenarioLocalReplayE2ETestCase,
    PostgresSnapshotApplyE2ETestCase,
    PostgresSnapshotE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    assert_current_postgres_snapshot_rows_from_case,
    assert_postgres_snapshot_apply_rows,
    assert_postgres_snapshot_matrix_rows,
    build_postgres_project_toml,
    build_unique_schema_name,
    cleanup_postgres_schema,
    ensure_postgres_schema_ready,
    fetch_postgres_rows,
    prepare_postgres_waffle_shop,
    relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    assert_optional_local_replay_rows,
    build_real_warehouse_local_replay_project_files,
    maybe_corrupt_scenario_snapshot_dialect,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    build_current_check_customers_model_sql,
    build_current_customers_model_sql,
    build_current_delete_customers_model_sql,
    build_historical_check_daily_model_sql,
    build_historical_timestamp_extracts_model_sql,
    build_real_warehouse_existing_snapshot_project_files,
    build_real_warehouse_snapshot_project_files,
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresBuildE2ETestCase(
            description="waffle shop full build succeeds on postgres",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["waffle shop full build succeeds on postgres"],
)
def test_given_waffle_shop_when_running_full_build_on_postgres_then_expected_table_exists(
    tmp_path: Path,
    test_case: PostgresBuildE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_postgres_waffle_shop(
        tmp_path=tmp_path, config=postgres_e2e_config
    )
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
            config=postgres_e2e_config,
        )
        row_count: object = rows[0][0]
        assert isinstance(row_count, int)
        assert row_count == test_case.expected_row_count
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


POSTGRES_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES: list[PostgresScenarioLocalReplayE2ETestCase] = [
    PostgresScenarioLocalReplayE2ETestCase(
        description="captures postgres fixtures and replays transpilable SQL locally",
        model_sql=(
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  customer_id,\n"
            "  DATE_TRUNC('day', event_ts) AS event_day,\n"
            "  SUM(CASE WHEN amount_cents >= 1000 THEN amount_cents ELSE 0 END)"
            " AS large_amount_cents,\n"
            "  COUNT(*) AS event_count\n"
            'FROM __source("raw_events")\n'
            "GROUP BY customer_id, DATE_TRUNC('day', event_ts)\n"
        ),
        scenario_sql=(
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_events AS (\n"
            "  SELECT 10 AS customer_id, CAST('2026-01-01 08:15:00' AS TIMESTAMP)"
            " AS event_ts, 1500 AS amount_cents\n"
            "  UNION ALL\n"
            "  SELECT 10 AS customer_id, CAST('2026-01-01 10:30:00' AS TIMESTAMP)"
            " AS event_ts, 500 AS amount_cents\n"
            "),\n"
            "__expected__event_rollup AS (\n"
            "  SELECT 10 AS customer_id,"
            " DATE_TRUNC('day', CAST('2026-01-01 00:00:00' AS TIMESTAMP)) AS event_day,"
            " 1500 AS large_amount_cents, 2 AS event_count\n"
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
    PostgresScenarioLocalReplayE2ETestCase(
        description="reports postgres local transpilation failures as X607",
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
]


@pytest.mark.parametrize(
    "test_case",
    POSTGRES_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES,
    ids=[case.description for case in POSTGRES_SCENARIO_LOCAL_REPLAY_E2E_TEST_CASES],
)
def test_given_postgres_scenario_capture_when_replaying_locally_then_transpilable_sql_passes(
    tmp_path: Path,
    test_case: PostgresScenarioLocalReplayE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqb_scenario_local")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_scenario_local_replay",
        repo_files=build_real_warehouse_local_replay_project_files(
            project_toml=build_postgres_project_toml(
                project_name="postgres_scenario_local_replay",
                schema_name=schema_name,
                config=postgres_e2e_config,
            ),
            model_sql=test_case.model_sql,
            scenario_sql=test_case.scenario_sql,
            scenario_name=test_case.scenario_name,
        ),
    )
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)

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
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresSnapshotE2ETestCase(
            description="executes snapshot scd2 matrix on postgres",
            expected_current_rows_after_initial_build=(("1", "10", "basic", "2026-01-01", None),),
            expected_current_rows_after_recovery=(
                ("1", "10", "basic", "2026-01-01", "2026-01-02"),
                ("1", "10", "pro", "2026-01-02", None),
            ),
            expected_historical_timestamp_rows=(
                ("1", "basic", "2026-01-01", "2026-01-03"),
                ("1", "pro", "2026-01-03", None),
                ("2", "trial", "2026-01-02", None),
            ),
            expected_historical_check_rows=(
                ("1", "active", "2026-01-01", "2026-01-03"),
                ("1", "paused", "2026-01-03", None),
                ("2", "active", "2026-01-01", "2026-01-02"),
            ),
            expected_failure_fragments=(
                "current_customer_snapshot",
                "delta audit for 'current_customer_snapshot' failed before target update",
            ),
        )
    ],
    ids=["executes snapshot scd2 matrix on postgres"],
)
def test_given_snapshot_project_when_building_on_postgres_then_scd2_history_is_valid(
    tmp_path: Path,
    test_case: PostgresSnapshotE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqb_snapshot")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_snapshot_project",
        repo_files=build_real_warehouse_snapshot_project_files(
            project_toml=build_postgres_project_toml(
                project_name="postgres_snapshot_project",
                schema_name=schema_name,
                config=postgres_e2e_config,
            ),
        ),
    )
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)

    try:
        initial_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
        assert_postgres_snapshot_matrix_rows(
            schema_name=schema_name,
            config=postgres_e2e_config,
            expected_current_rows=test_case.expected_current_rows_after_initial_build,
            expected_historical_timestamp_rows=test_case.expected_historical_timestamp_rows,
            expected_historical_check_rows=test_case.expected_historical_check_rows,
        )

        (project_dir / "models" / "current_customers.sql").write_text(
            build_current_customers_model_sql(plan="blocked", updated_at="2026-01-02 00:00:00"),
            encoding="utf-8",
        )
        failure_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--concurrency",
                "4",
                "--select",
                "+current_customer_snapshot",
            ),
            project_dir=project_dir,
        )
        assert failure_result.returncode == 1, failure_result.stdout + failure_result.stderr
        for fragment in test_case.expected_failure_fragments:
            assert fragment in failure_result.stdout + failure_result.stderr
        assert_current_postgres_snapshot_rows_from_case(
            schema_name=schema_name,
            config=postgres_e2e_config,
            expected_rows=test_case.expected_current_rows_after_initial_build,
        )

        (project_dir / "models" / "current_customers.sql").write_text(
            build_current_customers_model_sql(plan="pro", updated_at="2026-01-02 00:00:00"),
            encoding="utf-8",
        )
        recovery_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--concurrency",
                "4",
                "--select",
                "+current_customer_snapshot",
            ),
            project_dir=project_dir,
        )
        assert recovery_result.returncode == 0, recovery_result.stdout + recovery_result.stderr
        assert_current_postgres_snapshot_rows_from_case(
            schema_name=schema_name,
            config=postgres_e2e_config,
            expected_rows=test_case.expected_current_rows_after_recovery,
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresSnapshotApplyE2ETestCase(
            description="applies existing-target snapshot changes on postgres",
            expected_current_check_rows=(
                ("1", "active", "False"),
                ("1", "paused", "True"),
                ("2", "active", "True"),
            ),
            expected_current_delete_rows=(
                ("1", "basic", "False"),
                ("1", "pro", "True"),
                ("2", "trial", "False"),
            ),
            expected_historical_timestamp_rows=(
                ("1", "basic", "2026-01-01", "2026-01-03"),
                ("1", "pro", "2026-01-03", None),
                ("2", "trial", "2026-01-01", "2026-01-04"),
            ),
            expected_historical_check_rows=(
                ("1", "active", "2026-01-01", "2026-01-03"),
                ("1", "paused", "2026-01-03", None),
                ("2", "active", "2026-01-01", "2026-01-02"),
            ),
        )
    ],
    ids=["applies existing-target snapshot changes on postgres"],
)
def test_given_existing_snapshot_targets_when_building_on_postgres_then_apply_sql_succeeds(
    tmp_path: Path,
    test_case: PostgresSnapshotApplyE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqb_snapshot_apply")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_snapshot_apply_project",
        repo_files=build_real_warehouse_existing_snapshot_project_files(
            project_toml=build_postgres_project_toml(
                project_name="postgres_snapshot_apply_project",
                schema_name=schema_name,
                config=postgres_e2e_config,
            ),
        ),
    )
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)

    try:
        initial_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

        (project_dir / "models" / "current_check_customers.sql").write_text(
            build_current_check_customers_model_sql(changed=True), encoding="utf-8"
        )
        (project_dir / "models" / "current_delete_customers.sql").write_text(
            build_current_delete_customers_model_sql(changed=True), encoding="utf-8"
        )
        (project_dir / "models" / "historical_timestamp_extracts.sql").write_text(
            build_historical_timestamp_extracts_model_sql(changed=True), encoding="utf-8"
        )
        (project_dir / "models" / "historical_check_daily.sql").write_text(
            build_historical_check_daily_model_sql(changed=True), encoding="utf-8"
        )

        apply_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--concurrency", "4"),
            project_dir=project_dir,
        )
        assert apply_result.returncode == 0, apply_result.stdout + apply_result.stderr
        assert_postgres_snapshot_apply_rows(
            schema_name=schema_name,
            config=postgres_e2e_config,
            expected_current_check_rows=test_case.expected_current_check_rows,
            expected_current_delete_rows=test_case.expected_current_delete_rows,
            expected_historical_timestamp_rows=test_case.expected_historical_timestamp_rows,
            expected_historical_check_rows=test_case.expected_historical_check_rows,
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
