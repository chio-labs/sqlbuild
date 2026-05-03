from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entry.main import _main_with_dependencies, main
from sqlbuild.cli.commands.main.entry.models import CliEntrypointHandlers
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    MainErrorRenderingTestCase,
    MainTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="returns zero for root help",
            argv=["--help"],
            expected_exit_code=0,
        )
    ],
    ids=["returns zero for root help"],
)
def test_given_root_help_arguments_when_running_main_then_it_returns_expected_exit_code(
    test_case: MainTestCase,
) -> None:
    exit_code: int = main(test_case.argv)

    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        MainErrorRenderingTestCase(
            description="renders discovery errors without a traceback",
            argv=["--project-dir", "/tmp/demo", "compile"],
            expected_stderr_fragment=(
                "/tmp/demo/sqlbuild_project.yml must define non-empty string 'name'"
            ),
            expected_exit_code=1,
        )
    ],
    ids=["renders discovery errors without a traceback"],
)
def test_given_expected_cli_errors_when_running_main_then_it_renders_stderr_and_returns_one(
    test_case: MainErrorRenderingTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_compile(project_dir: Path | None) -> int:
        assert project_dir is not None
        raise ProjectConfigError(
            f"{project_dir / 'sqlbuild_project.yml'} must define non-empty string 'name'"
        )

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=CliEntrypointHandlers(run_compile=run_compile),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in rendered_stderr
