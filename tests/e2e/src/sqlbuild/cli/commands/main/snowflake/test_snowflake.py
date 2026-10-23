from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    assert_dbt_local_replay_rows,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    maybe_corrupt_scenario_snapshot_dialect,
)
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake._test_types import (
    SnowflakeBuildE2ETestCase,
    SnowflakeCliTestCase,
    SnowflakeCloneE2ETestCase,
    SnowflakeDbtProfileE2ETestCase,
    SnowflakeDbtScenarioLocalReplayE2ETestCase,
    SnowflakeDiffE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake.helpers import (
    build_snowflake_dbt_profiles_yml,
    cleanup_snowflake_schema,
    ensure_query_schema_ready,
    execute_snowflake_sql,
    fetch_snowflake_rows,
    prepare_snowflake_diff_project,
    prepare_snowflake_waffle_shop,
    relation_name,
    write_local_environment_override,
    write_snowflake_dbt_scenario_date_trunc_model,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    assert_dbt_profile_lifecycle,
    prepare_dbt_profile_workspace,
    run_sqb,
)
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    build_snowflake_connection_config,
    build_unique_schema_name,
)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeDbtProfileE2ETestCase(
            description="dbt init generated project builds through Snowflake PAT dbt profile",
            schema_prefix="sqlbuild_dbt_profile",
            expected_toml_fragments=(
                'adapter = "snowflake"',
                'source = "dbt_profile"',
                'profile = "analytics"',
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_dbt_profile_when_running_dbt_init_then_builds_profile_lifecycle(
    tmp_path: Path,
    test_case: SnowflakeDbtProfileE2ETestCase,
) -> None:
    schema_name: str = build_unique_schema_name(prefix=test_case.schema_prefix)
    config: dict[str, object] = build_snowflake_connection_config(schema=schema_name)
    database_name: str = str(config["database"])
    try:
        ensure_query_schema_ready(schema_name=schema_name)
        assert_dbt_profile_lifecycle(
            tmp_path=tmp_path,
            profiles_yml=(
                "analytics:\n"
                "  target: dev\n"
                "  outputs:\n"
                "    dev:\n"
                "      type: snowflake\n"
                f"      account: {config['account']}\n"
                f"      user: {config['user']}\n"
                "      authenticator: programmatic_access_token\n"
                f"      token: {config['token']}\n"
                f"      role: {config['role']}\n"
                f"      warehouse: {config['warehouse']}\n"
                f"      database: {database_name}\n"
                f"      schema: {schema_name}\n"
            ),
            env=None,
            fetch_rows=lambda sql: fetch_snowflake_rows(schema_name=schema_name, sql=sql),
            no_profile_tables_exist=lambda: (
                fetch_snowflake_rows(
                    schema_name=schema_name,
                    sql=(
                        f"SELECT LOWER(table_name) FROM {database_name}.information_schema.tables "
                        f"WHERE UPPER(table_schema) = UPPER('{schema_name}') "
                        "AND LOWER(table_name) IN ('dbt_orders', 'downstream_orders') "
                        "ORDER BY LOWER(table_name)"
                    ),
                )
                == ()
            ),
            dbt_orders_sql=(
                f"SELECT order_id FROM {relation_name(schema_name=schema_name, name='dbt_orders')} "
                "ORDER BY order_id"
            ),
            downstream_orders_sql=(
                "SELECT order_id FROM "
                f"{relation_name(schema_name=schema_name, name='downstream_orders')} "
                "ORDER BY order_id"
            ),
            expected_toml_fragments=test_case.expected_toml_fragments,
            unexpected_toml_fragments=(str(config["token"]),),
        )
    finally:
        cleanup_snowflake_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCliTestCase(
            description="query command uses snowflake local override",
            command=(
                "query",
                "SELECT CURRENT_DATABASE() AS database_name, CURRENT_SCHEMA() AS schema_name",
            ),
            expected_stdout_fragments=("DATABASE_NAME | SQB_DB", "SCHEMA_NAME   |"),
            expected_schema_fragment="SQLBUILD_E2E_",
        ),
        SnowflakeCliTestCase(
            description="query command renders json output",
            command=("query", "SELECT 1 AS id, 'alice' AS name", "--format", "json"),
            expected_stdout_fragments=('"ID": 1', '"NAME": "alice"'),
        ),
        SnowflakeCliTestCase(
            description="query command renders csv output",
            command=("query", "SELECT 1 AS id, 'alice' AS name", "--format", "csv"),
            expected_stdout_fragments=("ID,NAME", "1,alice"),
        ),
        SnowflakeCliTestCase(
            description="query command prints ok for ddl statements",
            command=("query", "CREATE OR REPLACE TEMP TABLE __sqb_query_temp (id INTEGER)"),
            expected_stdout_fragments=("OK",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_local_config_when_running_query_then_outputs_expected_rows(
    tmp_path: Path,
    test_case: SnowflakeCliTestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_snowflake_waffle_shop(tmp_path=tmp_path)
    ensure_query_schema_ready(schema_name=schema_name)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        assert "Cost" in result.stdout
        run_artifacts: tuple[Path, ...] = tuple(
            (project_dir / "target" / "executions").glob("*/run.json")
        )
        assert len(run_artifacts) == 1
        run_payload: dict[str, Any] = json.loads(run_artifacts[0].read_text(encoding="utf-8"))
        assert run_payload["adapter_name"] == "snowflake"
        assert run_payload["build_status"] == "success"
        assert run_payload["cost"]["rate_source"] == "default"
        assert "estimated_compute_credits" in run_payload["cost"]
        assert (run_artifacts[0].parent / "statements.jsonl").is_file()
        cost_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "cost", "latest", "--json"),
            project_dir=project_dir,
        )
        assert cost_result.returncode == 0, cost_result.stdout + cost_result.stderr
        cost_payload: dict[str, Any] = json.loads(cost_result.stdout)
        assert cost_payload["schema_version"] == 1
        assert cost_payload["run_id"] == run_payload["run_id"]
        assert test_case.expected_schema_fragment in result.stdout
    finally:
        cleanup_snowflake_schema(schema_name=schema_name)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeDbtScenarioLocalReplayE2ETestCase(
            description="captures snowflake dbt scenario and replays date_trunc locally",
            scenario_name="dbt_event_rollup",
            expected_stdout_fragments=(
                "dbt_event_rollup",
                "expect    expected event_rollup",
                "PASS=1  FAIL=0  ERROR=0  SKIP=0  TOTAL=1",
            ),
            expected_local_rows=((10, 2),),
            local_rows_sql=(
                "SELECT customer_id, event_count "
                "FROM __sqb_local__model__event_rollup ORDER BY customer_id"
            ),
        ),
        SnowflakeDbtScenarioLocalReplayE2ETestCase(
            description="reports snowflake dbt local transpilation failure as X607",
            scenario_name="dbt_event_rollup",
            expected_stdout_fragments=(
                "dbt_event_rollup",
                "ERROR",
                "error[X607]",
                "PASS=0  FAIL=0  ERROR=1  SKIP=0  TOTAL=1",
            ),
            expected_return_code=1,
            corrupt_capture_dialect=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_dbt_scenario_capture_when_replaying_locally_then_transpiles_to_duckdb(
    tmp_path: Path,
    test_case: SnowflakeDbtScenarioLocalReplayE2ETestCase,
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_dbt_scenario_local")
    config: dict[str, object] = build_snowflake_connection_config(schema=schema_name)
    workspace: Path = prepare_dbt_profile_workspace(
        tmp_path=tmp_path,
        profiles_yml=build_snowflake_dbt_profiles_yml(schema_name=schema_name, config=config),
    )
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    try:
        ensure_query_schema_ready(schema_name=schema_name)
        init_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "dbt",
                "init",
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--skip-dbt-debug",
            ),
            project_dir=workspace,
        )
        assert init_result.returncode == 0, init_result.stdout + init_result.stderr
        write_snowflake_dbt_scenario_date_trunc_model(sqlbuild_project_dir=sqlbuild_project_dir)
        execute_snowflake_sql(
            schema_name=schema_name,
            sql=(
                f"CREATE TABLE {relation_name(schema_name=schema_name, name='events')} "
                "(customer_id INTEGER, event_ts TIMESTAMP_NTZ)"
            ),
        )

        capture_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "scenario", "capture", test_case.scenario_name),
            project_dir=sqlbuild_project_dir,
        )
        assert capture_result.returncode == 0, capture_result.stdout + capture_result.stderr
        maybe_corrupt_scenario_snapshot_dialect(
            project_dir=sqlbuild_project_dir,
            scenario_name=test_case.scenario_name,
            enabled=test_case.corrupt_capture_dialect,
        )

        replay_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "scenario", "test", test_case.scenario_name, "--local"),
            project_dir=sqlbuild_project_dir,
        )

        assert replay_result.returncode == test_case.expected_return_code, (
            replay_result.stdout + replay_result.stderr
        )
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in replay_result.stdout
        assert_dbt_local_replay_rows(
            project_dir=sqlbuild_project_dir,
            scenario_name=test_case.scenario_name,
            rows_sql=test_case.local_rows_sql,
            expected_rows=test_case.expected_local_rows,
        )
    finally:
        cleanup_snowflake_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBuildE2ETestCase(
            description="waffle shop full build succeeds on snowflake",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_udf_rows=((1, True), (10, False)),
            expected_python_udf_rows=((1, True), (10, False)),
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_waffle_shop_when_running_full_build_on_snowflake_then_expected_table_exists(
    tmp_path: Path,
    test_case: SnowflakeBuildE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_snowflake_waffle_shop(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
            schema_name=schema_name,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
        )
        row_count: object = rows[0][0]
        assert isinstance(row_count, int)
        assert row_count == test_case.expected_row_count
        udf_rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
            schema_name=schema_name,
            sql=(
                "SELECT order_id, is_completed_order FROM "
                f"{relation_name(schema_name=schema_name, name='fact_orders')} "
                "WHERE order_id IN (1, 10) ORDER BY order_id"
            ),
        )
        assert udf_rows == test_case.expected_udf_rows
        python_udf_rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
            schema_name=schema_name,
            sql=(
                "SELECT order_id, is_completed_order_py FROM "
                f"{relation_name(schema_name=schema_name, name='fact_orders')} "
                "WHERE order_id IN (1, 10) ORDER BY order_id"
            ),
        )
        assert python_udf_rows == test_case.expected_python_udf_rows
    finally:
        cleanup_snowflake_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeDiffE2ETestCase(
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
        SnowflakeDiffE2ETestCase(
            description="full diff reports row mismatch",
            mutation_sql=(
                "UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 1",
            ),
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
        SnowflakeDiffE2ETestCase(
            description="verbose diff shows changed row examples",
            mutation_sql=(
                "UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 1",
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
            expected_stdout_fragments=("Examples", "order_id=1 | 100 -> 105"),
            expected_return_code=1,
        ),
        SnowflakeDiffE2ETestCase(
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
        SnowflakeDiffE2ETestCase(
            description="bounded diff reports mismatch inside bounded window",
            mutation_sql=(
                "UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 2",
            ),
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--bounded",
                "7d",
                "--select",
                "stg_orders",
            ),
            expected_stdout_fragments=("amount_cents", "mismatches=1", "order_id=2 | 200 -> 205"),
            expected_return_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_project_when_running_diff_then_outputs_expected_summary(
    tmp_path: Path,
    test_case: SnowflakeDiffE2ETestCase,
) -> None:
    project_dir: Path
    prod_schema: str
    dev_schema: str
    project_dir, prod_schema, dev_schema = prepare_snowflake_diff_project(tmp_path=tmp_path)

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
            execute_snowflake_sql(
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
        cleanup_snowflake_schema(schema_name=prod_schema)
        cleanup_snowflake_schema(schema_name=dev_schema)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCloneE2ETestCase(
            description="clone defaults to zero copy and hard copy uses CTAS",
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
    ids=lambda case: case.description,
)
def test_given_snowflake_project_when_cloning_then_default_uses_zero_copy_and_hard_copy_ctas(
    tmp_path: Path,
    test_case: SnowflakeCloneE2ETestCase,
) -> None:
    project_dir: Path
    prod_schema: str
    dev_schema: str
    project_dir, prod_schema, dev_schema = prepare_snowflake_diff_project(tmp_path=tmp_path)

    try:
        write_local_environment_override(project_dir=project_dir, environment="prod")
        prod_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert prod_build.returncode == 0, prod_build.stdout + prod_build.stderr
        ensure_query_schema_ready(schema_name=dev_schema)

        default_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.default_command,
            project_dir=project_dir,
        )
        assert default_result.returncode == 0, default_result.stdout + default_result.stderr
        fragment: str
        for fragment in test_case.expected_default_stdout_fragments:
            assert fragment in default_result.stdout
        cloned_rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
            schema_name=dev_schema,
            sql=(
                "SELECT order_id, customer_id, amount_cents FROM "
                f"{relation_name(schema_name=dev_schema, name='stg_orders')} ORDER BY order_id"
            ),
        )
        assert cloned_rows == test_case.expected_rows

        execute_snowflake_sql(
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
        copied_rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
            schema_name=dev_schema,
            sql=(
                "SELECT order_id, customer_id, amount_cents FROM "
                f"{relation_name(schema_name=dev_schema, name='stg_orders')} ORDER BY order_id"
            ),
        )
        assert copied_rows == test_case.expected_rows
    finally:
        cleanup_snowflake_schema(schema_name=prod_schema)
        cleanup_snowflake_schema(schema_name=dev_schema)
