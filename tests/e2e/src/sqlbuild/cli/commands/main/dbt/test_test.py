from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtExecutionFailureCliTestCase,
    DbtExecutionQueryAssertion,
    DbtTestCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    compile_dbt_interop_manifest,
    install_dbt_interop_packages,
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
    write_chained_dbt_seed_sqlbuild_unit_test,
    write_chained_dbt_source_sqlbuild_unit_test,
    write_dbt_model_sqlbuild_unit_test,
    write_dbt_seed_fixture_name_collision_sqlbuild_unit_test,
    write_dbt_seed_relation_collision_sqlbuild_unit_test,
    write_dbt_seed_sqlbuild_unit_test,
    write_dbt_source_fixture_name_collision_sqlbuild_unit_test,
    write_dbt_source_relation_collision_sqlbuild_unit_test,
    write_dbt_source_sqlbuild_unit_test,
    write_incremental_dbt_model_sqlbuild_unit_test,
    write_mocked_snapshot_boundary_dbt_sqlbuild_unit_test,
    write_qualified_dbt_model_sqlbuild_unit_test,
    write_qualified_dbt_seed_sqlbuild_unit_test,
    write_qualified_dbt_source_sqlbuild_unit_test,
    write_unmocked_snapshot_boundary_dbt_sqlbuild_unit_test,
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
        setup_command=("dbt", "build", "--select", "tag:nightly", "+downstream_orders"),
        command=("dbt", "test", "--select", "tag:nightly"),
        expected_stdout_fragments=(
            "dbt execution",
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
        expected_stdout_fragments=("dbt execution", "PASS"),
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
            "Skipping dbt tests: no dbt tests for the selection.",
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
            "dbt execution",
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
            "dbt execution",
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
DBT_SQL_TEST_TARGET_FAILURE_TEST_CASES: list[DbtExecutionFailureCliTestCase] = [
    DbtExecutionFailureCliTestCase(
        description="dbt source relation collision fails SQLBuild dbt test target",
        command=("dbt", "test", "--select", "stg_orders_from_source"),
        setup=write_dbt_source_relation_collision_sqlbuild_unit_test,
        expected_stdout_fragments=("same relation as SQLBuild source",),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb test", "PASS"),
    ),
    DbtExecutionFailureCliTestCase(
        description="dbt seed relation collision fails SQLBuild dbt test target",
        command=("dbt", "test", "--select", "dim_local_countries"),
        setup=write_dbt_seed_relation_collision_sqlbuild_unit_test,
        expected_stdout_fragments=("same relation as SQLBuild seed",),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb test", "PASS"),
    ),
    DbtExecutionFailureCliTestCase(
        description="unmocked dbt snapshot in chain fails SQLBuild dbt test target",
        command=("dbt", "test", "--select", "fact_orders_snapshot"),
        setup=write_unmocked_snapshot_boundary_dbt_sqlbuild_unit_test,
        expected_stdout_fragments=("snapshot",),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb test", "PASS"),
    ),
]
DBT_SQL_TEST_FIXTURE_FAILURE_TEST_CASES: list[DbtExecutionFailureCliTestCase] = [
    DbtExecutionFailureCliTestCase(
        description="dbt source fixture name collision fails SQLBuild dbt test target",
        command=("dbt", "test", "--select", "stg_orders_from_source"),
        setup=write_dbt_source_fixture_name_collision_sqlbuild_unit_test,
        expected_stdout_fragments=("conflicts with a SQLBuild source",),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb test", "PASS"),
    ),
    DbtExecutionFailureCliTestCase(
        description="dbt seed fixture name collision fails SQLBuild dbt test target",
        command=("dbt", "test", "--select", "dim_countries"),
        setup=write_dbt_seed_fixture_name_collision_sqlbuild_unit_test,
        expected_stdout_fragments=("conflicts with a SQLBuild seed",),
        expected_absent_stdout_fragments=("SQLBuild execution  sqb test", "PASS"),
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
            description="SQLBuild unit test targets dbt model with mocked upstream",
            setup_command=("dbt", "build", "--select", "+fact_orders"),
            command=("dbt", "test", "--select", "fact_orders"),
            expected_stdout_fragments=(
                "dbt execution",
                "SQLBuild execution  sqb test",
                "test_dbt_fact_orders",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets dbt model with mocked upstream"],
)
def test_given_sqlbuild_test_targets_dbt_model_when_running_dbt_test_then_uses_mocked_upstream(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_model_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets package-qualified dbt model",
            setup_command=("dbt", "build", "--select", "+fact_orders"),
            command=("dbt", "test", "--select", "fact_orders"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_fact_orders",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets package-qualified dbt model"],
)
def test_given_sqlbuild_test_targets_qualified_dbt_model_when_running_dbt_test_then_passes(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_qualified_dbt_model_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild dbt test compiles incremental target with full refresh",
            setup_command=("dbt", "build", "--select", "+fact_orders"),
            command=("dbt", "test", "--select", "fact_orders"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_fact_orders",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild dbt test compiles incremental target with full refresh"],
)
def test_given_incremental_dbt_test_target_when_running_dbt_test_then_uses_full_refresh_sql(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_incremental_dbt_model_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets dbt model with source mock",
            setup_command=("dbt", "plan", "--select", "stg_orders_from_source"),
            command=("dbt", "test", "--select", "stg_orders_from_source"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_stg_orders_from_source",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets dbt model with source mock"],
)
def test_given_sqlbuild_test_targets_dbt_source_model_when_running_dbt_test_then_uses_source_mock(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_source_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets dbt model with seed mock",
            setup_command=("dbt", "plan", "--select", "dim_countries"),
            command=("dbt", "test", "--select", "dim_countries"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_dim_countries",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets dbt model with seed mock"],
)
def test_given_sqlbuild_test_targets_dbt_seed_model_when_running_dbt_test_then_uses_seed_mock(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_dbt_seed_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets chained dbt source model",
            setup_command=("dbt", "plan", "--select", "fact_orders_from_source"),
            command=("dbt", "test", "--select", "fact_orders_from_source"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_fact_orders_from_source",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets chained dbt source model"],
)
def test_given_chained_dbt_source_model_when_running_dbt_test_then_resolves_chain(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_chained_dbt_source_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets chained dbt seed model",
            setup_command=("dbt", "plan", "--select", "dim_country_names"),
            command=("dbt", "test", "--select", "dim_country_names"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_dim_country_names",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets chained dbt seed model"],
)
def test_given_chained_dbt_seed_model_when_running_dbt_test_then_resolves_chain(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_chained_dbt_seed_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test mocks dbt snapshot boundary",
            setup_command=("dbt", "plan", "--select", "fact_orders_snapshot"),
            command=("dbt", "test", "--select", "fact_orders_snapshot"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_fact_orders_snapshot",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test mocks dbt snapshot boundary"],
)
def test_given_mocked_snapshot_boundary_when_running_dbt_test_then_uses_mock_boundary(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_mocked_snapshot_boundary_dbt_sqlbuild_unit_test(project_dir=project_dir)
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets dbt model with qualified source mock",
            setup_command=("dbt", "plan", "--select", "stg_orders_from_qualified_source"),
            command=("dbt", "test", "--select", "stg_orders_from_qualified_source"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_stg_orders_from_qualified_source",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets dbt model with qualified source mock"],
)
def test_given_qualified_dbt_source_fixture_when_running_dbt_test_then_uses_source_mock(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_qualified_dbt_source_sqlbuild_unit_test(project_dir=project_dir)
    deps_result: subprocess.CompletedProcess[str] = install_dbt_interop_packages(
        project_dir=project_dir
    )
    assert deps_result.returncode == 0, deps_result.stderr or deps_result.stdout
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="SQLBuild unit test targets dbt model with qualified seed mock",
            setup_command=("dbt", "plan", "--select", "dim_qualified_countries"),
            command=("dbt", "test", "--select", "dim_qualified_countries"),
            expected_stdout_fragments=(
                "SQLBuild execution  sqb test",
                "test_dbt_dim_qualified_countries",
                "PASS",
            ),
        )
    ],
    ids=["SQLBuild unit test targets dbt model with qualified seed mock"],
)
def test_given_qualified_dbt_seed_fixture_when_running_dbt_test_then_uses_seed_mock(
    test_case: DbtTestCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    write_qualified_dbt_seed_sqlbuild_unit_test(project_dir=project_dir)
    deps_result: subprocess.CompletedProcess[str] = install_dbt_interop_packages(
        project_dir=project_dir
    )
    assert deps_result.returncode == 0, deps_result.stderr or deps_result.stdout
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


@pytest.mark.parametrize(
    "test_case",
    DBT_SQL_TEST_TARGET_FAILURE_TEST_CASES,
    ids=[case.description for case in DBT_SQL_TEST_TARGET_FAILURE_TEST_CASES],
)
def test_given_dbt_relation_collision_when_running_dbt_test_then_fails_before_sqlbuild_test(
    test_case: DbtExecutionFailureCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    test_case.setup(project_dir)
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--select", test_case.command[-1]),
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode
    output: str = result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in output
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    DBT_SQL_TEST_FIXTURE_FAILURE_TEST_CASES,
    ids=[case.description for case in DBT_SQL_TEST_FIXTURE_FAILURE_TEST_CASES],
)
def test_given_dbt_fixture_name_collision_when_running_dbt_test_then_fails_during_compile(
    test_case: DbtExecutionFailureCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    test_case.setup(project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode
    output: str = result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in output
    absent_stdout_fragment: str
    for absent_stdout_fragment in test_case.expected_absent_stdout_fragments:
        assert absent_stdout_fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtTestCliTestCase(
            description="failing dbt test stops before SQLBuild validation",
            setup_command=("dbt", "run", "--select", "+fact_orders"),
            command=("dbt", "test", "--select", "tag:nightly"),
            expected_stdout_fragments=("dbt execution",),
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
