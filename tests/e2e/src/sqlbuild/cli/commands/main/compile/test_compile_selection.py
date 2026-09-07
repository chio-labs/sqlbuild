"""E2E coverage for focused offline compilation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileSelectionTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        CompileSelectionTestCase(
            description="selected models compile without unrelated contract diagnostics",
            selection_args=("--select", "order_record", "result"),
            expected_stdout_fragments=(
                "Compile ready  2 models",
                "order_record",
                "result",
                "Project compiled  2 models",
            ),
            unexpected_stdout_fragments=("unrelated", "error[K001]"),
        ),
        CompileSelectionTestCase(
            description="exclude-only selection compiles every other model",
            selection_args=("--exclude", "unrelated"),
            expected_stdout_fragments=(
                "Compile ready  2 models",
                "order_record",
                "result",
                "Project compiled  2 models",
            ),
            unexpected_stdout_fragments=("unrelated", "error[K001]"),
        ),
        CompileSelectionTestCase(
            description="select file keeps upstream analysis while reporting its downstream",
            selection_args=("--select-file", "selectors.txt"),
            expected_stdout_fragments=(
                "Compile ready  1 model",
                "result",
                "Project compiled  1 model",
            ),
            unexpected_stdout_fragments=("order_record", "unrelated", "error[K001]"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_selection_when_compiling_then_limits_offline_analysis_and_report(
    test_case: CompileSelectionTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="compile_selection",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "compile_selection"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = ":memory:"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
            ),
            "models/order_record.sql": "MODEL ();\n\nSELECT 1 AS order_id\n",
            "models/result.sql": (
                'MODEL (columns (order_id ()));\n\nSELECT order_id FROM __ref("order_record")\n'
            ),
            "models/unrelated.sql": (
                "MODEL (columns (missing_column ()));\n\nSELECT 1 AS present_column\n"
            ),
            "selectors.txt": "result\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "compile",
            *test_case.selection_args,
            "--no-sql-validation",
        ),
        project_dir=project_dir,
        working_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    for fragment in test_case.unexpected_stdout_fragments:
        assert fragment not in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
