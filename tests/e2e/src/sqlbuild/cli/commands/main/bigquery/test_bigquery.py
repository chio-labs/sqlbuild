from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.bigquery._test_types import (
    BigQueryBuildE2ETestCase,
    BigQueryCliTestCase,
    BigQueryCloneE2ETestCase,
    BigQueryDbtProfileE2ETestCase,
    BigQueryDiffE2ETestCase,
    BigQueryErrorE2ETestCase,
    BigQueryModelBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.bigquery.helpers import (
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
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    assert_dbt_profile_lifecycle,
    run_sqb,
)
from tests.integration.src.sqlbuild.adapters.bigquery.helpers import (
    build_bigquery_connection_config,
    build_unique_dataset_name,
)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryDbtProfileE2ETestCase(
            description="dbt init generated project builds through BigQuery dbt profile",
            schema_prefix="sqlbuild_dbt_profile",
            expected_toml_fragments=(
                'adapter = "bigquery"',
                'source = "dbt_profile"',
                'profile = "analytics"',
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_dbt_profile_when_running_dbt_init_then_builds_profile_lifecycle(
    tmp_path: Path,
    test_case: BigQueryDbtProfileE2ETestCase,
) -> None:
    dataset_name: str = build_unique_dataset_name(prefix=test_case.schema_prefix)
    config: dict[str, object] = build_bigquery_connection_config(schema=dataset_name)
    project_id: str = str(config["project"])
    try:
        ensure_bigquery_dataset_ready(dataset_name=dataset_name)
        assert_dbt_profile_lifecycle(
            tmp_path=tmp_path,
            profiles_yml=(
                "analytics:\n"
                "  target: dev\n"
                "  outputs:\n"
                "    dev:\n"
                "      type: bigquery\n"
                "      method: oauth\n"
                f"      project: {project_id}\n"
                f"      dataset: {dataset_name}\n"
                f"      location: {config['location']}\n"
            ),
            env=None,
            fetch_rows=lambda sql: fetch_bigquery_rows(dataset_name=dataset_name, sql=sql),
            no_profile_tables_exist=lambda: (
                fetch_bigquery_rows(
                    dataset_name=dataset_name,
                    sql=(
                        "SELECT table_name FROM "
                        f"`{project_id}.{dataset_name}.INFORMATION_SCHEMA.TABLES` "
                        "WHERE table_name IN ('dbt_orders', 'downstream_orders') "
                        "ORDER BY table_name"
                    ),
                )
                == ()
            ),
            dbt_orders_sql=(
                "SELECT order_id FROM "
                f"{relation_name(dataset_name=dataset_name, name='dbt_orders')} "
                "ORDER BY order_id"
            ),
            downstream_orders_sql=(
                "SELECT order_id FROM "
                f"{relation_name(dataset_name=dataset_name, name='downstream_orders')} "
                "ORDER BY order_id"
            ),
            expected_toml_fragments=test_case.expected_toml_fragments,
        )
    finally:
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
        diagnostic_path: Path = tuple((project_dir / "logs").glob("*/*/diagnostics.jsonl"))[0]
        diagnostic_records: tuple[dict[str, object], ...] = tuple(
            map(json.loads, diagnostic_path.read_text(encoding="utf-8").splitlines())
        )
        assert "TIMESTAMP_TRUNC(" in hourly_sql
        assert "TIMESTAMP_TRUNC(" in daily_sql
        assert "TIMESTAMP_TRUNC(" in contextual_sql
        assert "`" in order_status_sql
        sql_diagnostics: tuple[dict[str, object], ...] = tuple(
            filter(lambda record: record["logger"] == "sqlbuild.sql", diagnostic_records)
        )
        assert sql_diagnostics
        for diagnostic in sql_diagnostics:
            fields: object = diagnostic["fields"]
            assert isinstance(fields, dict)
            assert "sql_digest" in fields
            assert "sql_text" not in fields
    finally:
        cleanup_bigquery_dataset(dataset_name=dataset_name)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryErrorE2ETestCase(
            description="query preserves underlying error",
            command=("query", "SELECT missing_column FROM UNNEST([STRUCT(1 AS id)])"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
        "MODEL (description 'Test model bigquery_broken_model.', materialized table);\n\nSELECT missing_column FROM UNNEST([STRUCT(1 AS id)])",
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
    [
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
        BigQueryDiffE2ETestCase(
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
            mutation_sql=(
                "UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 2",
            ),
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
    ],
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryCloneE2ETestCase(
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
def test_given_bigquery_project_when_cloning_then_default_uses_zero_copy_and_hard_copy_ctas(
    tmp_path: Path,
    test_case: BigQueryCloneE2ETestCase,
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
        ensure_bigquery_dataset_ready(dataset_name=dev_dataset)

        default_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.default_command,
            project_dir=project_dir,
        )
        assert default_result.returncode == 0, default_result.stdout + default_result.stderr
        fragment: str
        for fragment in test_case.expected_default_stdout_fragments:
            assert fragment in default_result.stdout
        cloned_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dev_dataset,
            sql=(
                "SELECT order_id, customer_id, amount_cents FROM "
                f"{relation_name(dataset_name=dev_dataset, name='stg_orders')} ORDER BY order_id"
            ),
        )
        assert cloned_rows == test_case.expected_rows

        execute_bigquery_sql(
            dataset_name=dev_dataset,
            sql=f"DROP TABLE {relation_name(dataset_name=dev_dataset, name='stg_orders')}",
        )
        hard_copy_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.hard_copy_command,
            project_dir=project_dir,
        )
        assert hard_copy_result.returncode == 0, hard_copy_result.stdout + hard_copy_result.stderr
        for fragment in test_case.expected_hard_copy_stdout_fragments:
            assert fragment in hard_copy_result.stdout
        copied_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=dev_dataset,
            sql=(
                "SELECT order_id, customer_id, amount_cents FROM "
                f"{relation_name(dataset_name=dev_dataset, name='stg_orders')} ORDER BY order_id"
            ),
        )
        assert copied_rows == test_case.expected_rows
    finally:
        cleanup_bigquery_dataset(dataset_name=prod_dataset)
        cleanup_bigquery_dataset(dataset_name=dev_dataset)
