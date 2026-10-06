"""Test helpers never share a name with model CTEs or relations through the real DuckDB CLI."""

import shutil
from pathlib import Path
from subprocess import CompletedProcess

import duckdb
import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    FixtureProjectIsolationE2ETestCase,
    HelperIsolationE2ETestCase,
    IsolatedCompileE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    assert_test_query_names_isolated,
    build_helper_scope_project_files,
    build_lookup_project_files,
    build_shared_cte_name_chain_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    REPO_ROOT,
    WAFFLE_SHOP_DIR,
    prepare_inline_project,
    run_sqb,
)

_PASSING_ORDER_LINES_SQL: str = "SELECT 1 AS order_id, 20 AS line_total"


@pytest.mark.parametrize(
    "test_case",
    (
        HelperIsolationE2ETestCase(
            description="analysed models read the physical table, not the fixture helper",
            sql_analysis_enabled=True,
            expected_output_fragments=("PASS=1  FAIL=0",),
        ),
        HelperIsolationE2ETestCase(
            description="textual models read the physical table, not the fixture helper",
            sql_analysis_enabled=False,
            expected_output_fragments=("PASS=1  FAIL=0",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_helper_named_like_relations_models_read_when_testing_then_models_read_their_own(
    tmp_path: Path, test_case: HelperIsolationE2ETestCase
) -> None:
    project: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="lookup",
        repo_files=build_lookup_project_files(sql_analysis_enabled=test_case.sql_analysis_enabled),
    )
    with duckdb.connect(str(project / "lookup.duckdb")) as connection:
        connection.execute("CREATE TABLE main.lookup_rows AS SELECT 1 AS order_id")

    tested: CompletedProcess[str] = run_sqb(command=("--no-color", "test"), project_dir=project)

    output: str = tested.stdout + tested.stderr
    assert tested.returncode == 0, output
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    sql: str = next((project / "target" / "run" / "tests").rglob("lookup.sql")).read_text()
    assert_test_query_names_isolated(sql, ("lookup_rows",))


@pytest.mark.parametrize(
    "test_case",
    (
        FixtureProjectIsolationE2ETestCase(
            description="e2e waffle shop fixture",
            project_dir=WAFFLE_SHOP_DIR,
            expected_minimum_tests=1,
        ),
        FixtureProjectIsolationE2ETestCase(
            description="website waffle shop example",
            project_dir=REPO_ROOT / "website" / "examples" / "waffle-shop",
            expected_minimum_tests=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_fixture_project_when_compiling_tests_then_cte_names_are_isolated(
    tmp_path: Path, test_case: FixtureProjectIsolationE2ETestCase
) -> None:
    project: Path = tmp_path / test_case.project_dir.name
    shutil.copytree(test_case.project_dir, project)

    compiled: CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project
    )

    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    paths: list[Path] = sorted((project / "target" / "compiled" / "tests").rglob("*.sql"))
    assert len(paths) >= test_case.expected_minimum_tests
    for path in paths:
        assert_test_query_names_isolated(path.read_text(), ())


@pytest.mark.parametrize(
    "test_case",
    (
        IsolatedCompileE2ETestCase(
            description="analysed chain with shared model and helper CTE names",
            project_files=build_shared_cte_name_chain_project_files(
                sql_analysis_enabled=True, expected_order_lines_sql=_PASSING_ORDER_LINES_SQL
            ),
            compile_arguments=(),
            helper_names=("base_rows", "expected_rows"),
            expected_minimum_tests=1,
        ),
        IsolatedCompileE2ETestCase(
            description="textual chain with shared model and helper CTE names",
            project_files=build_shared_cte_name_chain_project_files(
                sql_analysis_enabled=False, expected_order_lines_sql=_PASSING_ORDER_LINES_SQL
            ),
            compile_arguments=("--no-sql-analysis",),
            helper_names=("base_rows", "expected_rows"),
            expected_minimum_tests=1,
        ),
        IsolatedCompileE2ETestCase(
            description="analysed helpers read by expected rows and assertions",
            project_files=build_helper_scope_project_files(),
            compile_arguments=(),
            helper_names=("doubled", "expected_rows"),
            expected_minimum_tests=1,
        ),
        IsolatedCompileE2ETestCase(
            description="textual helpers read by expected rows and assertions",
            project_files=build_helper_scope_project_files(),
            compile_arguments=("--no-sql-analysis",),
            helper_names=("doubled", "expected_rows"),
            expected_minimum_tests=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_helper_projects_when_compiling_tests_then_helpers_keep_no_top_level_name(
    tmp_path: Path, test_case: IsolatedCompileE2ETestCase
) -> None:
    project: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="isolation", repo_files=test_case.project_files
    )

    compiled: CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile", *test_case.compile_arguments), project_dir=project
    )

    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    paths: list[Path] = sorted((project / "target" / "compiled" / "tests").rglob("*.sql"))
    assert len(paths) >= test_case.expected_minimum_tests
    for path in paths:
        assert_test_query_names_isolated(path.read_text(), test_case.helper_names)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
