from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.databricks._test_types import (
    DatabricksBuildE2ETestCase,
    DatabricksCliTestCase,
    DatabricksCloneE2ETestCase,
    DatabricksDbtProfileE2ETestCase,
    DatabricksDiffE2ETestCase,
    DatabricksErrorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.databricks.helpers import (
    cleanup_databricks_schema,
    databricks_e2e_timing,
    ensure_databricks_schema_ready,
    execute_databricks_sql,
    fetch_databricks_rows,
    prepare_databricks_diff_project,
    prepare_databricks_query_source,
    prepare_databricks_waffle_shop,
    relation_name,
    write_local_environment_override,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    assert_dbt_profile_lifecycle,
    run_sqb,
)
from tests.integration.src.sqlbuild.adapters.databricks.helpers import (
    build_databricks_connection_config,
    build_unique_schema_name,
)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksDbtProfileE2ETestCase(
            description="dbt init generated project builds through Databricks dbt profile",
            schema_prefix="sqlbuild_dbt_profile",
            expected_toml_fragments=(
                'adapter = "databricks"',
                'source = "dbt_profile"',
                'profile = "analytics"',
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_databricks_dbt_profile_when_running_dbt_init_then_builds_profile_lifecycle(
    tmp_path: Path,
    test_case: DatabricksDbtProfileE2ETestCase,
) -> None:
    schema_name: str = build_unique_schema_name(prefix=test_case.schema_prefix)
    config: dict[str, object] = build_databricks_connection_config(schema=schema_name)
    catalog_name: str = str(config["catalog"])
    try:
        ensure_databricks_schema_ready(schema_name=schema_name)
        assert_dbt_profile_lifecycle(
            tmp_path=tmp_path,
            profiles_yml=(
                "analytics:\n"
                "  target: dev\n"
                "  outputs:\n"
                "    dev:\n"
                "      type: databricks\n"
                f"      host: {config['server_hostname']}\n"
                f"      http_path: {config['http_path']}\n"
                f"      token: {config['token']}\n"
                f"      catalog: {catalog_name}\n"
                f"      schema: {schema_name}\n"
            ),
            env=None,
            fetch_rows=lambda sql: fetch_databricks_rows(schema_name=schema_name, sql=sql),
            no_profile_tables_exist=lambda: (
                fetch_databricks_rows(
                    schema_name=schema_name,
                    sql=(
                        f"SELECT table_name FROM `{catalog_name}`.information_schema.tables "
                        f"WHERE table_schema = '{schema_name}' "
                        "AND table_name IN ('dbt_orders', 'downstream_orders') ORDER BY table_name"
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
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
)
def test_given_waffle_shop_when_running_full_build_on_databricks_then_expected_values_exist(
    tmp_path: Path,
    test_case: DatabricksBuildE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    with databricks_e2e_timing("prepare waffle shop fixture"):
        project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)

    try:
        with databricks_e2e_timing("sqb build"):
            result: subprocess.CompletedProcess[str] = run_sqb(
                command=test_case.command,
                project_dir=project_dir,
            )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        with databricks_e2e_timing("post-build verification queries"):
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
        with databricks_e2e_timing("cleanup schema"):
            cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
        "MODEL (description 'Test model databricks_broken_model.', materialized table);\n\nSELECT missing_column FROM (SELECT 1 AS id)",
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
