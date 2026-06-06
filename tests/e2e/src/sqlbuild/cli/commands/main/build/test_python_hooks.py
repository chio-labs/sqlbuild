"""E2E tests for Python lifecycle hooks in sqb build."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    PythonHookFailureBuildE2ETestCase,
    PythonHooksBuildE2ETestCase,
    SnapshotPythonHooksBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHooksBuildE2ETestCase(
            description="build executes Python pre and post hooks",
            expected_exit_code=0,
            expected_orders_rows=((42, "created by hook"),),
            expected_hook_log_rows=(("orders", "orders", "post"),),
        )
    ],
    ids=["build executes Python pre and post hooks"],
)
def test_given_project_with_python_hooks_when_building_then_hooks_execute(
    test_case: PythonHooksBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_hooks_build_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "python_hooks_build_project"
                adapter = "duckdb"

                [connection]
                database = "python_hooks_build_project.duckdb"
                """
            ).strip()
            + "\n",
            "hooks/lifecycle.py": dedent(
                """
                from sqlbuild.hooks import hook


                @hook
                def create_hook_data(ctx, value):
                    ctx.execute_sql(
                        f"CREATE TABLE {ctx.destination.schema}.hook_data AS "
                        f"SELECT {value} AS id, 'created by hook' AS label"
                    )


                @hook
                def record_hook_completion(ctx, phase):
                    ctx.execute_sql(
                        f"CREATE TABLE {ctx.destination.schema}.hook_log AS "
                        f"SELECT '{ctx.model_name}' AS model_name, "
                        f"'{ctx.destination.name}' AS relation_name, '{phase}' AS phase"
                    )
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  pre_hooks [python("create_hook_data", value: 42)],
                  post_hooks [python("record_hook_completion", phase: "post")]
                );

                SELECT id, label FROM main.hook_data
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stderr
    assert query_duckdb(
        db_path=project_dir / "python_hooks_build_project.duckdb",
        sql="SELECT id, label FROM main.orders",
    ) == list(test_case.expected_orders_rows)
    assert query_duckdb(
        db_path=project_dir / "python_hooks_build_project.duckdb",
        sql="SELECT model_name, relation_name, phase FROM main.hook_log",
    ) == list(test_case.expected_hook_log_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookFailureBuildE2ETestCase(
            description="post hook failure blocks downstream model",
            expected_exit_code=1,
            expected_output_fragments=(
                'post_hooks[0] python("fail_hook") failed: intentional post failure',
                "orders",
                "downstream_orders",
            ),
            expected_present_tables=("orders",),
            expected_absent_tables=("downstream_orders",),
        )
    ],
    ids=["post hook failure blocks downstream model"],
)
def test_given_python_post_hook_failure_when_building_graph_then_downstream_is_blocked(
    test_case: PythonHookFailureBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_hook_failure_build_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "python_hook_failure_build_project"
                adapter = "duckdb"

                [connection]
                database = "python_hook_failure_build_project.duckdb"
                """
            ).strip()
            + "\n",
            "hooks/lifecycle.py": dedent(
                """
                from sqlbuild.hooks import hook


                @hook
                def fail_hook(ctx, message):
                    raise RuntimeError(message)
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  post_hooks [python("fail_hook", message: "intentional post failure")]
                );

                SELECT 1 AS id
                """
            ).strip()
            + "\n",
            "models/downstream_orders.sql": dedent(
                """
                MODEL (materialized table);

                SELECT id FROM __ref("orders")
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "orders+"),
        project_dir=project_dir,
    )
    db_path: Path = project_dir / "python_hook_failure_build_project.duckdb"

    assert result.returncode == test_case.expected_exit_code, result.stderr
    for fragment in test_case.expected_output_fragments:
        assert fragment in result.stdout or fragment in result.stderr
    for table_name in test_case.expected_present_tables:
        assert table_exists(db_path=db_path, table_name=table_name)
    for table_name in test_case.expected_absent_tables:
        assert not table_exists(db_path=db_path, table_name=table_name)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotPythonHooksBuildE2ETestCase(
            description="snapshot build executes Python pre and post hooks",
            expected_exit_code=0,
            expected_snapshot_rows=((1, "basic", "2026-01-01 00:00:00", None),),
            expected_hook_log_rows=(("customer_snapshot", "post_hooks"),),
        )
    ],
    ids=["snapshot build executes Python pre and post hooks"],
)
def test_given_snapshot_with_python_hooks_when_building_then_hooks_execute(
    test_case: SnapshotPythonHooksBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="snapshot_python_hooks_build_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "snapshot_python_hooks_build_project"
                adapter = "duckdb"

                [connection]
                database = "snapshot_python_hooks_build_project.duckdb"
                """
            ).strip()
            + "\n",
            "hooks/snapshot_hooks.py": dedent(
                """
                from sqlbuild.hooks import hook


                @hook
                def create_snapshot_source(ctx):
                    ctx.execute_sql(
                        "CREATE TABLE main.raw_customers AS "
                        "SELECT 1 AS customer_id, 'basic' AS plan, "
                        "TIMESTAMP '2026-01-01 00:00:00' AS updated_at"
                    )


                @hook
                def log_snapshot_hook(ctx):
                    ctx.execute_sql(
                        f"CREATE TABLE {ctx.destination.schema}.snapshot_hook_log AS "
                        f"SELECT '{ctx.model_name}' AS model_name, '{ctx.phase}' AS phase"
                    )
                """
            ).strip()
            + "\n",
            "models/customer_snapshot.sql": dedent(
                """
                MODEL (
                  materialized snapshot,
                  unique_key [customer_id],
                  snapshot_strategy timestamp,
                  updated_at updated_at,
                  pre_hooks [python("create_snapshot_source")],
                  post_hooks [python("log_snapshot_hook")]
                );

                SELECT customer_id, plan, updated_at FROM main.raw_customers
                """
            ).strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    db_path: Path = project_dir / "snapshot_python_hooks_build_project.duckdb"

    assert result.returncode == test_case.expected_exit_code, result.stderr
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.customer_snapshot ORDER BY customer_id"
        ),
    ) == list(test_case.expected_snapshot_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT model_name, phase FROM main.snapshot_hook_log",
    ) == list(test_case.expected_hook_log_rows)
