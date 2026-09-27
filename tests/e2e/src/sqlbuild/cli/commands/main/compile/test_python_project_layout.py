"""E2E coverage for fail-closed Python project layout validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    PythonProjectLayoutCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        PythonProjectLayoutCompileTestCase(
            description="unsupported project Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "audit_helpers/measurements.py": "def build_cases(): return []\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): audit_helpers/measurements.py",
                "Move pipeline Python nodes and the helper modules they import under python/",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed tasks Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "tasks/orders.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): tasks/orders.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed assets Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "assets/orders.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): assets/orders.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed checks Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "checks/orders.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): checks/orders.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed loaders Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "loaders/orders.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): loaders/orders.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed factories Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "factories/orders.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): factories/orders.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed libs Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "libs/cleaning.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): libs/cleaning.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed dagster Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "dagster/definitions.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): dagster/definitions.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed rivers_pipeline Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "rivers_pipeline/definitions.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): rivers_pipeline/definitions.py",
            ),
        ),
        PythonProjectLayoutCompileTestCase(
            description="removed root definitions.py Python root",
            repo_files={
                "sqlbuild_project.toml": 'name = "python_layout"\nadapter = "duckdb"\n',
                "definitions.py": "from sqlbuild.tasks import task\n",
            },
            expected_exit_code=1,
            expected_stderr_fragments=(
                "error[D016]",
                "Unsupported project Python path(s): definitions.py",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_python_under_unsupported_root_when_compiling_then_command_fails_with_path_guidance(
    test_case: PythonProjectLayoutCompileTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_layout",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert all(fragment in result.stderr for fragment in test_case.expected_stderr_fragments)


@pytest.mark.parametrize(
    "test_case",
    (
        PythonProjectLayoutCompileTestCase(
            description="custom Rule harness test path",
            repo_files={
                "sqlbuild_project.toml": 'name = "rule_harness_layout"\nadapter = "duckdb"\n',
                "models/orders.sql": "MODEL ();\nSELECT 1 AS order_id\n",
                "tests/rules/test_order_policy.py": "def test_order_policy(): pass\n",
            },
            expected_exit_code=0,
            expected_stderr_fragments=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rule_harness_test_when_compiling_then_python_test_path_is_accepted(
    test_case: PythonProjectLayoutCompileTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="rule_harness_layout",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert "Project compiled  1 model" in result.stdout


@pytest.mark.parametrize(
    "test_case",
    (
        PythonProjectLayoutCompileTestCase(
            description="python root with nested nodes and undecorated helpers",
            repo_files={
                "sqlbuild_project.toml": (
                    'name = "python_root_layout"\n'
                    'adapter = "duckdb"\n'
                    'default_target = "dev"\n\n'
                    "[connections.developer]\n"
                    'database = "python_root_layout.duckdb"\n\n'
                    "[targets.dev]\n"
                    'connection = "developer"\n'
                    'schema = "main"\n'
                ),
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_orders\n"
                    "    managed: true\n"
                    "    write_strategy: table\n"
                    "    columns:\n"
                    "      - name: order_id\n"
                    "        type: INTEGER\n"
                    "      - name: status\n"
                    "        type: VARCHAR\n"
                ),
                "models/fact_orders.sql": (
                    "MODEL (materialized table);\n\n"
                    'SELECT order_id, status FROM __source("raw_orders")\n'
                ),
                "python/_helpers.py": (
                    "def normalize_status(value):\n    return value.strip().lower()\n"
                ),
                "python/orders/__init__.py": "",
                "python/orders/utils.py": (
                    "from python._helpers import normalize_status\n\n\n"
                    "def order_rows():\n"
                    "    return [\n"
                    "        {'order_id': 1, 'status': normalize_status(' Shipped ')},\n"
                    "        {'order_id': 2, 'status': normalize_status('PENDING')},\n"
                    "    ]\n"
                ),
                "python/loaders/orders.py": (
                    "from python.orders.utils import order_rows\n"
                    "from sqlbuild.loaders import loader\n\n\n"
                    "@loader\n"
                    "def raw_orders(ctx):\n"
                    "    return order_rows()\n"
                ),
                "python/orders/exports/assets.py": (
                    "from sqlbuild.assets import asset\n"
                    "from sqlbuild.refs import model\n\n\n"
                    "@asset(depends_on=model('fact_orders'))\n"
                    "def orders_export(ctx):\n"
                    "    relation = ctx.relation(model('fact_orders'))\n"
                    "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()\n"
                    "    return ctx.result(payload={'order_count': int(rows[0][0])})\n"
                ),
                "python/orders/exports/checks.py": (
                    "from python.orders.exports.assets import orders_export\n"
                    "from sqlbuild.checks import check\n\n\n"
                    "@check(depends_on=orders_export)\n"
                    "def orders_export_not_empty(ctx):\n"
                    "    payload = ctx.result_of(node_function=orders_export).payload\n"
                    "    if payload['order_count'] <= 0:\n"
                    "        return ctx.fail(message='orders export is empty')\n"
                    "    return ctx.pass_(message='orders export is ready')\n"
                ),
            },
            expected_exit_code=0,
            expected_stderr_fragments=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_python_root_project_when_compiling_and_building_then_nodes_run_with_helpers(
    test_case: PythonProjectLayoutCompileTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_root_layout",
        repo_files=test_case.repo_files,
    )

    compile_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"),
        project_dir=project_dir,
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    compile_output: str = compile_result.stdout + compile_result.stderr
    build_output: str = build_result.stdout + build_result.stderr
    assert compile_result.returncode == test_case.expected_exit_code, compile_output
    assert build_result.returncode == test_case.expected_exit_code, build_output
    assert all(
        fragment in build_output
        for fragment in (
            "raw_orders",
            "fact_orders",
            "orders_export",
            "orders_export_not_empty",
            "orders export is ready",
        )
    )
    assert "_helpers" not in build_output
    assert "order_rows" not in build_output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
