from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entry.main import _main_with_dependencies, main
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    MainErrorRenderingTestCase,
    MainTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.entry.helpers import build_handlers

ERROR_RENDERING_TEST_CASES: list[MainErrorRenderingTestCase] = [
    MainErrorRenderingTestCase(
        description="renders discovery errors without a traceback",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=ProjectConfigError,
        error_factory=lambda project_dir: ProjectConfigError(
            f"{project_dir / 'sqlbuild_project.yml'} must define non-empty string 'name'"
        ),
        expected_stderr_fragment=(
            "/tmp/demo/sqlbuild_project.yml must define non-empty string 'name'"
        ),
        expected_exit_code=1,
    ),
    MainErrorRenderingTestCase(
        description="renders cli user errors without a traceback",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=CliUserError,
        error_factory=lambda project_dir: CliUserError("bad command usage"),
        expected_stderr_fragment="bad command usage",
        expected_exit_code=1,
    ),
    MainErrorRenderingTestCase(
        description="renders plain value errors without a traceback",
        argv=["--project-dir", "/tmp/demo", "compile"],
        error_type=ValueError,
        error_factory=lambda project_dir: ValueError("invalid compile request"),
        expected_stderr_fragment="invalid compile request",
        expected_exit_code=1,
    ),
]


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
        MainTestCase(
            description="dispatches compile command through injected handler",
            argv=["--project-dir", "/tmp/demo", "compile"],
            expected_exit_code=7,
        )
    ],
    ids=["dispatches compile command through injected handler"],
)
def test_given_compile_command_arguments_when_running_with_dependencies_then_it_dispatches_handler(
    test_case: MainTestCase,
) -> None:
    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(
            run_compile=lambda *_a, **_k: test_case.expected_exit_code,
        ),
    )

    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes no sql validation flag to compile handler",
            argv=["compile", "--no-sql-validation"],
            expected_exit_code=3,
            expected_project_dir=None,
            expected_no_sql_validation=True,
        )
    ],
    ids=["passes no sql validation flag to compile handler"],
)
def test_given_compile_no_sql_validation_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[Path | None, bool, str | None, bool]] = []

    def run_compile(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        json_output: bool,
    ) -> int:
        received_args.append((project_dir, no_sql_validation, defer_to, json_output))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_compile=run_compile),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [
        (test_case.expected_project_dir, test_case.expected_no_sql_validation, None, False)
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes full refresh flag to build handler",
            argv=["build", "--full-refresh"],
            expected_exit_code=5,
            expected_full_refresh=True,
        )
    ],
    ids=["passes full refresh flag to build handler"],
)
def test_given_build_full_refresh_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[tuple[bool, bool]] = []

    def run_build(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        cursor_overrides: object,
        no_color: bool,
        fail_fast: bool,
        full_refresh: bool,
        concurrency: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool = False,
        debug: bool = False,
    ) -> int:
        del project_dir
        del no_sql_validation
        del defer_to
        del cursor_overrides
        del no_color
        del concurrency
        del select
        del exclude
        del verbose
        del debug
        received_args.append((fail_fast, full_refresh))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_build=run_build),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [(False, test_case.expected_full_refresh)]


@pytest.mark.parametrize(
    "test_case",
    [
        MainTestCase(
            description="passes full refresh flag to run handler",
            argv=["run", "--full-refresh"],
            expected_exit_code=6,
            expected_full_refresh=True,
        )
    ],
    ids=["passes full refresh flag to run handler"],
)
def test_given_run_full_refresh_when_running_then_dispatches_expected_flag(
    test_case: MainTestCase,
) -> None:
    received_args: list[bool] = []

    def run_run(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        cursor_overrides: object,
        no_color: bool,
        fail_fast: bool,
        full_refresh: bool,
        concurrency: int | None,
        select: tuple[str, ...],
        exclude: tuple[str, ...],
        verbose: bool = False,
        debug: bool = False,
    ) -> int:
        del project_dir
        del no_sql_validation
        del defer_to
        del cursor_overrides
        del no_color
        del fail_fast
        del concurrency
        del select
        del exclude
        del verbose
        del debug
        received_args.append(full_refresh)
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_run=run_run),
    )

    assert exit_code == test_case.expected_exit_code
    assert received_args == [test_case.expected_full_refresh]


@pytest.mark.parametrize(
    "test_case",
    ERROR_RENDERING_TEST_CASES,
    ids=[case.description for case in ERROR_RENDERING_TEST_CASES],
)
def test_given_expected_cli_errors_when_running_main_then_it_renders_stderr_and_returns_one(
    test_case: MainErrorRenderingTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_compile(
        project_dir: Path | None,
        no_sql_validation: bool,
        defer_to: str | None,
        json_output: bool,
    ) -> int:
        del no_sql_validation
        del defer_to
        del json_output
        assert project_dir is not None
        raise test_case.error_factory(project_dir)

    exit_code: int = _main_with_dependencies(
        argv=test_case.argv,
        handlers=build_handlers(run_compile=run_compile),
    )
    rendered_stderr: str = capsys.readouterr().err

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in rendered_stderr
