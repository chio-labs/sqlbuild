"""`sqb test` executes model SQL exactly as authored through the real DuckDB CLI."""

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import AuthoredSqlParityTestCase
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb
from tests.integration.src.sqlbuild.executor.testing.helpers import (
    build_authored_cte_project_files,
    build_terminated_model_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AuthoredSqlParityTestCase(
            description="comments and dollar quotes in CTE bodies",
            compiled_test_name="test_stg_orders.sql",
            expected_fragments=(
                "base AS (\n  -- a comment with an unmatched ) parenthesis\n"
                "  SELECT id AS order_id, amount, 'it''s (fine)' AS note /* ( */\n"
                "  FROM __source__raw_orders)",
                "tagged AS (SELECT order_id, amount, note, $$a ) b$$ AS tag FROM base)",
                "__actual__stg_orders AS (SELECT order_id, amount, note, tag FROM tagged)",
            ),
        ),
        AuthoredSqlParityTestCase(
            description="nested WITH and a fixture CTE collision use the nested fallback",
            compiled_test_name="test_orders.sql",
            expected_fragments=(
                "totals AS (\n"
                "  WITH ranked AS (SELECT order_id, amount, tag FROM __ref__stg_orders)\n"
                "  SELECT order_id, amount * 2 AS doubled, tag FROM ranked)",
                "helper_rows AS (SELECT order_id, doubled, tag FROM totals)",
                "__expected__orders AS (WITH helper_rows AS "
                "(SELECT 1 AS order_id, 20 AS doubled, 'x' AS tag) "
                "SELECT order_id, doubled, tag FROM helper_rows)",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_authored_ctes_when_testing_then_passes_and_runs_the_authored_sql(
    tmp_path: Path, test_case: AuthoredSqlParityTestCase
) -> None:
    project: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="authored_ctes",
        repo_files=build_authored_cte_project_files(),
    )

    tested: CompletedProcess[str] = run_sqb(command=("--no-color", "test"), project_dir=project)
    compiled: CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project
    )

    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert "PASS=2  FAIL=0" in tested.stdout, tested.stdout
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    sql: str = next(
        (project / "target" / "compiled" / "tests").rglob(test_case.compiled_test_name)
    ).read_text()
    for fragment in test_case.expected_fragments:
        assert fragment in sql, sql


@pytest.mark.parametrize(
    "test_case",
    (
        AuthoredSqlParityTestCase(
            description="a WITH model ending in a statement terminator",
            compiled_test_name="test_m.sql",
            expected_fragments=("__actual__m AS (SELECT id FROM a)",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_ending_in_semicolon_when_testing_then_terminator_is_dropped_and_passes(
    tmp_path: Path, test_case: AuthoredSqlParityTestCase
) -> None:
    project: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="terminated",
        repo_files=build_terminated_model_project_files(),
    )

    tested: CompletedProcess[str] = run_sqb(command=("--no-color", "test"), project_dir=project)
    compiled: CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project
    )

    assert tested.returncode == 0, tested.stdout + tested.stderr
    assert "PASS=1  FAIL=0" in tested.stdout, tested.stdout
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    sql: str = next(
        (project / "target" / "compiled" / "tests").rglob(test_case.compiled_test_name)
    ).read_text()
    for fragment in test_case.expected_fragments:
        assert fragment in sql, sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
