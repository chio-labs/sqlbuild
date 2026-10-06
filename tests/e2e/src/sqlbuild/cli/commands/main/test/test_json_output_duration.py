"""`sqb test --json-output` reports each SQL test's duration through the real DuckDB CLI."""

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import JsonDurationE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    build_shared_cte_name_chain_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        JsonDurationE2ETestCase(
            description="passing chain test reports its duration",
            expected_order_lines_sql="SELECT 1 AS order_id, 20 AS line_total",
            expected_exit_code=0,
            expected_status="pass",
        ),
        JsonDurationE2ETestCase(
            description="failing chain test reports its duration",
            expected_order_lines_sql="SELECT 1 AS order_id, 99 AS line_total",
            expected_exit_code=1,
            expected_status="fail",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_test_when_writing_json_output_then_check_reports_duration_ms(
    tmp_path: Path, test_case: JsonDurationE2ETestCase
) -> None:
    project: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="json_duration",
        repo_files=build_shared_cte_name_chain_project_files(
            sql_analysis_enabled=True,
            expected_order_lines_sql=test_case.expected_order_lines_sql,
        ),
    )
    json_path: Path = tmp_path / "result.json"

    result: CompletedProcess[str] = run_sqb(
        command=("--no-color", "test", "--json-output", str(json_path)), project_dir=project
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    checks: list[dict[str, object]] = json.loads(json_path.read_text())["checks"]
    assert [(check["name"], check["status"]) for check in checks] == [
        ("order_chain", test_case.expected_status)
    ], checks
    duration: object = checks[0].get("duration_ms")
    assert isinstance(duration, int) and duration >= 0, checks


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
