from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresBuildE2ETestCase,
    PostgresDbtProfileE2ETestCase,
    PostgresDbtSeedChangeE2ETestCase,
    PostgresPartialSourceTypeEnforcementE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    append_postgres_dbt_seed_change_order,
    build_postgres_project_toml,
    build_unique_schema_name,
    cleanup_postgres_schema,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    fetch_postgres_rows,
    postgres_dbt_env,
    prepare_postgres_dbt_seed_change_workspace,
    prepare_postgres_waffle_shop,
    relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    add_dbt_profile_downstream_model,
    prepare_dbt_profile_workspace,
    prepare_inline_project,
    run_sqb,
    stringify_warehouse_rows,
    write_dbt_profile_orders_model,
)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        PostgresDbtProfileE2ETestCase(
            description="dbt init generated project builds through postgres dbt profile",
            expected_toml_fragments=(
                'adapter = "postgres"',
                'source = "dbt_profile"',
                'profile = "analytics"',
                'target = "dev"',
            ),
            unexpected_toml_fragments=("DBT_POSTGRES_PASSWORD",),
            expected_initial_rows=((1,),),
            expected_changed_rows=((2,),),
            expected_rerun_fragments=("dbt execution", "SQLBuild execution"),
            expected_plain_selector_block_fragments=(
                "Skipping dbt: no dbt work selected.",
                'relation "',
                'dbt_orders" does not exist',
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_dbt_profile_when_running_dbt_init_then_plain_build_uses_profile(
    tmp_path: Path,
    test_case: PostgresDbtProfileE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_dbt_profile")
    workspace: Path = prepare_dbt_profile_workspace(
        tmp_path=tmp_path,
        profiles_yml=(
            "analytics:\n"
            "  target: dev\n"
            "  outputs:\n"
            "    dev:\n"
            "      type: postgres\n"
            f"      host: {postgres_e2e_config['host']}\n"
            f"      port: {postgres_e2e_config['port']}\n"
            f"      dbname: {postgres_e2e_config['dbname']}\n"
            f"      user: {postgres_e2e_config['user']}\n"
            "      pass: \"{{ env_var('DBT_POSTGRES_PASSWORD') }}\"\n"
            f"      schema: {schema_name}\n"
        ),
    )
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    env: dict[str, str] = postgres_dbt_env(password=str(postgres_e2e_config["password"]))
    try:
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
            env=env,
        )

        assert init_result.returncode == test_case.expected_return_code, (
            init_result.stdout + init_result.stderr
        )
        generated_toml: str = (sqlbuild_project_dir / "sqlbuild_project.toml").read_text(
            encoding="utf-8"
        )
        for fragment in test_case.expected_toml_fragments:
            assert fragment in generated_toml
        for fragment in test_case.unexpected_toml_fragments:
            assert fragment not in generated_toml

        add_dbt_profile_downstream_model(sqlbuild_project_dir=sqlbuild_project_dir)

        plain_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "downstream_orders"),
            project_dir=sqlbuild_project_dir,
            env=env,
        )

        assert plain_result.returncode != test_case.expected_return_code, (
            plain_result.stdout + plain_result.stderr
        )
        for fragment in test_case.expected_plain_selector_block_fragments:
            assert fragment in plain_result.stdout
        assert (
            fetch_postgres_rows(
                config=postgres_e2e_config,
                sql=(
                    "SELECT table_name FROM information_schema.tables "
                    f"WHERE table_schema = '{schema_name}' "
                    "AND table_name IN ('dbt_orders', 'downstream_orders') "
                    "ORDER BY table_name"
                ),
            )
            == ()
        )

        first_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
            project_dir=sqlbuild_project_dir,
            env=env,
        )

        assert first_result.returncode == test_case.expected_return_code, (
            first_result.stdout + first_result.stderr
        )
        assert (
            fetch_postgres_rows(
                config=postgres_e2e_config,
                sql=f"SELECT order_id FROM {schema_name}.dbt_orders ORDER BY order_id",
            )
            == test_case.expected_initial_rows
        )
        assert (
            fetch_postgres_rows(
                config=postgres_e2e_config,
                sql=f"SELECT order_id FROM {schema_name}.downstream_orders ORDER BY order_id",
            )
            == test_case.expected_initial_rows
        )

        rerun_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
            project_dir=sqlbuild_project_dir,
            env=env,
        )

        assert rerun_result.returncode == test_case.expected_return_code, (
            rerun_result.stdout + rerun_result.stderr
        )
        for fragment in test_case.expected_rerun_fragments:
            assert fragment in rerun_result.stdout

        write_dbt_profile_orders_model(workspace=workspace, order_id=2)
        changed_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "+downstream_orders"),
            project_dir=sqlbuild_project_dir,
            env=env,
        )

        assert changed_result.returncode == test_case.expected_return_code, (
            changed_result.stdout + changed_result.stderr
        )
        assert (
            fetch_postgres_rows(
                config=postgres_e2e_config,
                sql=f"SELECT order_id FROM {schema_name}.dbt_orders ORDER BY order_id",
            )
            == test_case.expected_changed_rows
        )
        assert (
            fetch_postgres_rows(
                config=postgres_e2e_config,
                sql=f"SELECT order_id FROM {schema_name}.downstream_orders ORDER BY order_id",
            )
            == test_case.expected_changed_rows
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


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
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresPartialSourceTypeEnforcementE2ETestCase(
            description="postgres partial source type enforcement preserves extra columns",
            expected_rows=(("7", "loaded-dev", "99"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_source_type_enforcement_when_building_on_postgres_then_casts_columns(
    tmp_path: Path,
    test_case: PostgresPartialSourceTypeEnforcementE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_src_cast")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_partial_source_type_enforcement",
        repo_files={
            "sqlbuild_project.toml": build_postgres_project_toml(
                project_name="postgres_partial_source_type_enforcement",
                schema_name=schema_name,
                config=postgres_e2e_config,
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n    description: Test source raw_orders.\n"
                f"    schema: {schema_name}\n"
                "    type_enforcement: true\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/stg_orders.sql": (
                "MODEL (description 'Test model stg_orders.', materialized table);\n\n"
                'SELECT order_id, status, amount_cents FROM __source("raw_orders")'
            ),
        },
    )
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)

    try:
        execute_postgres_sql(
            config=postgres_e2e_config,
            sql=(
                f"CREATE TABLE {relation_name(schema_name=schema_name, name='raw_orders')} "
                "(order_id TEXT, status VARCHAR, amount_cents INTEGER)"
            ),
        )
        execute_postgres_sql(
            config=postgres_e2e_config,
            sql=(
                f"INSERT INTO {relation_name(schema_name=schema_name, name='raw_orders')} "
                "VALUES ('7', 'loaded-dev', 99)"
            ),
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            config=postgres_e2e_config,
            sql=(
                "SELECT order_id, status, amount_cents FROM "
                f"{relation_name(schema_name=schema_name, name='stg_orders')} "
                "ORDER BY order_id"
            ),
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        PostgresDbtSeedChangeE2ETestCase(
            description="postgres dbt seed change and ordinary rerun execute the selected graph",
            expected_initial_total=75,
            expected_changed_total=115,
            expected_changed_fragments=("dbt execution", "fct_orders"),
            expected_rerun_fragments=("dbt execution", "fct_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_dbt_seed_change_when_building_then_ordinary_rerun_executes_graph(
    tmp_path: Path,
    test_case: PostgresDbtSeedChangeE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_dbt_seed_change")
    project_dir: Path = prepare_postgres_dbt_seed_change_workspace(
        tmp_path=tmp_path,
        schema_name=schema_name,
        config=postgres_e2e_config,
    )
    env: dict[str, str] = postgres_dbt_env(password=str(postgres_e2e_config["password"]))
    try:
        baseline: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "+fct_orders"),
            project_dir=project_dir,
            env=env,
        )
        assert baseline.returncode == 0, baseline.stdout + baseline.stderr
        assert fetch_postgres_rows(
            config=postgres_e2e_config,
            sql=f"SELECT total_amount FROM {schema_name}.fct_orders",
        ) == ((test_case.expected_initial_total,),)

        append_postgres_dbt_seed_change_order(project_dir=project_dir, order_id=4, amount=40)

        changed: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "+fct_orders"),
            project_dir=project_dir,
            env=env,
        )
        assert changed.returncode == 0, changed.stdout + changed.stderr
        fragment: str
        for fragment in test_case.expected_changed_fragments:
            assert fragment in changed.stdout
        assert fetch_postgres_rows(
            config=postgres_e2e_config,
            sql=f"SELECT total_amount FROM {schema_name}.fct_orders",
        ) == ((test_case.expected_changed_total,),)

        rerun: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "dbt", "build", "--select", "+fct_orders"),
            project_dir=project_dir,
            env=env,
        )
        assert rerun.returncode == 0, rerun.stdout + rerun.stderr
        for fragment in test_case.expected_rerun_fragments:
            assert fragment in rerun.stdout
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)
