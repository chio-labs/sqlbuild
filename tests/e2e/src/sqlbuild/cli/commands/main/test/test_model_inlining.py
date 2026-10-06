"""Each model in a SQL test is inlined once, in its own scope, through the real DuckDB CLI."""

from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import ModelInliningE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    ORDER_TOTALS_EXPECTED_ROWS_SQL,
    build_shared_cte_name_chain_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_SINGLE_OCCURRENCE_FRAGMENTS: tuple[str, ...] = (
    "__ref__order_lines AS (",
    "__ref__order_totals AS (",
    "amount * 2 AS line_total",
    "line_total + 1 AS order_total",
    "base_rows AS (SELECT 1 AS order_id, 10 AS amount)",
    f"expected_rows AS ({ORDER_TOTALS_EXPECTED_ROWS_SQL})",
)
_EXPECTED_FRAGMENTS: tuple[str, ...] = (
    "__actual__order_lines AS (SELECT * FROM __ref__order_lines)",
    "__actual__order_totals AS (SELECT * FROM __ref__order_totals)",
)
_PASSING_ORDER_LINES_SQL: str = "SELECT 1 AS order_id, 20 AS line_total"


@pytest.mark.parametrize(
    "test_case",
    (
        ModelInliningE2ETestCase(
            description="analysed chain with shared final CTEs passes",
            sql_analysis_enabled=True,
            expected_order_lines_sql=_PASSING_ORDER_LINES_SQL,
            expected_exit_code=0,
            expected_output_fragments=("PASS=1  FAIL=0",),
        ),
        ModelInliningE2ETestCase(
            description="textual chain with shared final CTEs passes",
            sql_analysis_enabled=False,
            expected_order_lines_sql=_PASSING_ORDER_LINES_SQL,
            expected_exit_code=0,
            expected_output_fragments=("PASS=1  FAIL=0",),
        ),
        ModelInliningE2ETestCase(
            description="wrong upstream expectation fails on the upstream model only",
            sql_analysis_enabled=True,
            expected_order_lines_sql="SELECT 1 AS order_id, 99 AS line_total",
            expected_exit_code=1,
            expected_output_fragments=(
                "PASS=0  FAIL=1",
                "unexpected sample 1: order_id=1, line_total=20",
                "missing sample 1: order_id=1, line_total=99",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_chained_models_sharing_cte_names_when_testing_then_each_model_is_inlined_once(
    tmp_path: Path, test_case: ModelInliningE2ETestCase
) -> None:
    project: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="model_inlining",
        repo_files=build_shared_cte_name_chain_project_files(
            sql_analysis_enabled=test_case.sql_analysis_enabled,
            expected_order_lines_sql=test_case.expected_order_lines_sql,
        ),
    )

    tested: CompletedProcess[str] = run_sqb(command=("--no-color", "test"), project_dir=project)
    compiled: CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project
    )

    output: str = tested.stdout + tested.stderr
    assert tested.returncode == test_case.expected_exit_code, output
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    for artifact_root in ("run", "compiled"):
        sql: str = next(
            (project / "target" / artifact_root / "tests").rglob("order_chain.sql")
        ).read_text()
        for fragment in _SINGLE_OCCURRENCE_FRAGMENTS:
            assert sql.count(fragment) == 1, f"{fragment!r} in {artifact_root}:\n{sql}"
        for fragment in _EXPECTED_FRAGMENTS:
            assert fragment in sql, sql
        assert "WITH expected_rows" not in sql, sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
