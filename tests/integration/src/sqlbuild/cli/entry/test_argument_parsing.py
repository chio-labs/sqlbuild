from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.entry._test_types import (
    ParserErrorTestCase,
    SelectorCompileTestCase,
)
from tests.integration.src.sqlbuild.cli.entry.helpers import (
    PYTHON_CLI,
    LauncherRun,
    run,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ParserErrorTestCase(
            description="type converter rejection",
            args=("compile", "--vars", "[1]"),
            expected_usage=b"usage: sqb compile ",
            expected_error=b"sqb compile: error[C900]: argument --vars: --vars must be a JSON object",
        ),
        ParserErrorTestCase(
            description="post-parse concurrency rule",
            args=("build", "--concurrency", "0"),
            expected_usage=b"usage: sqb [-h]",
            expected_error=b"sqb: error[C900]: --concurrency must be >= 1",
        ),
        ParserErrorTestCase(
            description="mutually exclusive options",
            args=("lineage", "orders", "--json", "--format", "tree"),
            expected_usage=b"usage: sqb lineage ",
            expected_error=(
                b"sqb lineage: error[C900]: argument --format: not allowed with argument --json"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rejected_arguments_when_running_sqb_then_usage_and_coded_error_exit_two(
    test_case: ParserErrorTestCase, tmp_path: Path
) -> None:
    exit_code, stdout, stderr = run(PYTHON_CLI, args=test_case.args, cwd=tmp_path)

    assert (exit_code, stdout) == (2, b"")
    assert stderr.startswith(test_case.expected_usage)
    assert stderr.endswith(test_case.expected_error + b"\n\n")


@pytest.mark.parametrize(
    "test_case",
    [
        SelectorCompileTestCase(
            description="positional selector",
            args=("compile", "orders", "--json"),
            expected_model=b"orders",
        ),
        SelectorCompileTestCase(
            description="positional selector after an option",
            args=("compile", "--json", "orders"),
            expected_model=b"orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_positional_selector_when_compiling_then_the_selected_model_compiles(
    test_case: SelectorCompileTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "project")

    completed: LauncherRun = run(PYTHON_CLI, args=test_case.args, cwd=project_dir)

    exit_code, stdout, _ = completed
    assert exit_code == 0
    assert test_case.expected_model in stdout


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
