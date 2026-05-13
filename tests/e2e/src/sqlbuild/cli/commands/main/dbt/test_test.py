from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtExecutionQueryAssertion,
    DbtTestCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    compile_dbt_interop_manifest,
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    query_duckdb,
    run_sqb,
    table_exists,
)

pytestmark: pytest.MarkDecorator = pytest.mark.dbt

DBT_TEST_COMMAND_TEST_CASES: list[DbtTestCliTestCase] = [
    DbtTestCliTestCase(
        description="test executes mixed dbt and SQLBuild validation work",
        setup_command=("dbt", "build", "--select", "tag:nightly"),
        command=("dbt", "test", "--select", "tag:nightly"),
        expected_stdout_fragments=(
            "Running dbt:",
            "SQLBuild execution  sqb test",
            "SQLBuild execution  sqb audit",
            "test_downstream_orders",
            "not_null",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="mixed test uses prebuilt downstream relation",
                sql="SELECT order_id FROM main.downstream_orders ORDER BY order_id",
                expected_rows=((1,),),
            ),
        ),
    ),
    DbtTestCliTestCase(
        description="test executes dbt only validation work",
        setup_command=("dbt", "run", "--select", "dbt_only"),
        command=("dbt", "test", "--select", "dbt_only"),
        expected_stdout_fragments=("Running dbt:", "PASS"),
        expected_absent_stdout_fragments=("SQLBuild execution",),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="dbt only test uses prebuilt dbt relation",
                sql="SELECT order_id FROM main.dbt_only",
                expected_rows=((2,),),
            ),
        ),
    ),
    DbtTestCliTestCase(
        description="test executes SQLBuild only validation work",
        setup_command=("dbt", "build", "--select", "local_only"),
        command=("dbt", "test", "--select", "local_only"),
        expected_stdout_fragments=(
            "Skipping dbt: no dbt work selected.",
            "SQLBuild execution  sqb test",
            "SQLBuild execution  sqb audit",
            "test_local_only",
            "not_null",
        ),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="sqlbuild only test uses prebuilt local relation",
                sql="SELECT order_id FROM main.local_only",
                expected_rows=((10,),),
            ),
        ),
    ),
    DbtTestCliTestCase(
        description="test type data maps SQLBuild side to audits only",
        setup_command=(
            "dbt",
            "build",
            "--select",
            "stg_orders",
            "fact_orders",
            "dbt_only",
            "local_only",
        ),
        command=("dbt", "test", "--select", "test_type:data", "local_only"),
        expected_stdout_fragments=(
            "Running dbt:",
            "SQLBuild execution  sqb audit",
            "not_null",
        ),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb test", "test_local_only"),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="data test leaves local relation available for audits",
                sql="SELECT order_id FROM main.local_only",
                expected_rows=((10,),),
            ),
        ),
    ),
    DbtTestCliTestCase(
        description="test type unit maps SQLBuild side to tests only",
        setup_command=("dbt", "build", "--select", "local_only"),
        command=("dbt", "test", "--select", "test_type:unit", "local_only"),
        expected_stdout_fragments=(
            "Running dbt:",
            "SQLBuild execution  sqb test",
            "test_local_only",
        ),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb audit", "not_null"),
        expected_query_assertions=(
            DbtExecutionQueryAssertion(
                description="unit test leaves local relation available for SQLBuild tests",
                sql="SELECT order_id FROM main.local_only",
                expected_rows=((10,),),
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DBT_TEST_COMMAND_TEST_CASES,
    ids=[case.description for case in DBT_TEST_COMMAND_TEST_CASES],
)
def test_given_prebuilt_dbt_interop_project_when_running_test_then_executes_expected_validation(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.setup_command,
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in result.stdout
    db_path: Path = project_dir / "dbt_interop.duckdb"
    query_assertion: DbtExecutionQueryAssertion
    for query_assertion in test_case.expected_query_assertions:
        assert query_duckdb(db_path=db_path, sql=query_assertion.sql) == list(
            query_assertion.expected_rows
        ), query_assertion.description


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test mocks package-qualified dbt refs",
            setup_command=("dbt", "compile"),
            command=("--no-color", "test", "--select", "downstream_orders"),
            expected_stdout_fragments=(
                "Execution  sqb test",
                "test_downstream_orders",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test mocks package-qualified dbt refs"],
)
def test_given_dbt_manifest_when_running_sqlbuild_test_then_mocks_dbt_refs(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = compile_dbt_interop_manifest(
        project_dir=project_dir
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="failing dbt test stops before SQLBuild validation",
            setup_command=("dbt", "run", "--select", "+fact_orders"),
            command=("dbt", "test", "--select", "tag:nightly"),
            expected_stdout_fragments=("Running dbt:",),
            expected_absent_stdout_fragments=("SQLBuild execution",),
        )
    ],
    ids=["failing dbt test stops before SQLBuild validation"],
)
def test_given_failing_dbt_test_when_running_test_then_sqlbuild_validation_does_not_run(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    stg_orders_path: Path = (
        project_dir.parent / "dbt_project" / "models" / "staging" / "stg_orders.sql"
    )
    stg_orders_path.write_text(
        "{{ config(tags=['nightly', 'staging']) }}\n\n"
        "select null as order_id, cast('2026-01-01 00:00:00' as timestamp) as ordered_at\n",
        encoding="utf-8",
    )
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.setup_command,
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 1
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in result.stdout
    db_path: Path = project_dir / "dbt_interop.duckdb"
    assert table_exists(db_path=db_path, table_name="fact_orders")
    assert not table_exists(db_path=db_path, table_name="downstream_orders")
