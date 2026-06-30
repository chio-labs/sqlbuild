from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.commands.dbt import run_dbt_command
from sqlbuild.integrations.dbt.models import DbtInitRequest, DbtInitResult, DbtInteropPlan
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from tests.unit.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtAutoInitTestCase,
    DbtDebugWrapperTestCase,
    DbtExecutionWrapperTestCase,
    DbtPlanProgressTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.dbt.helpers import (
    build_empty_dbt_plan,
    prepare_dbt_auto_init_dirs,
    write_minimal_sqlbuild_project,
)

PROGRESS_TEST_CASES: list[DbtPlanProgressTestCase] = [
    DbtPlanProgressTestCase(
        description="human output writes progress and plan to stdout",
        json_output=False,
        expected_stdout_fragments=(
            "Compiling dbt project...",
            "Generated dbt interop plan.",
            "Plan ready",
        ),
        expected_stderr_fragments=(),
    ),
    DbtPlanProgressTestCase(
        description="json output writes progress to stderr and json to stdout",
        json_output=True,
        expected_stdout_fragments=('"command": "plan"',),
        expected_stderr_fragments=(
            "Compiling dbt project...",
            "Generated dbt interop plan.",
        ),
    ),
]

EXECUTION_WRAPPER_TEST_CASES: list[DbtExecutionWrapperTestCase] = [
    DbtExecutionWrapperTestCase(
        description="dbt run strips local json and verbose flags before execution",
        command_name="run",
        args=("--json", "--verbose", "--select", "tag:nightly"),
        expected_forwarded_args=("--select", "tag:nightly"),
        expected_progress_stream_name="stderr",
    ),
    DbtExecutionWrapperTestCase(
        description="dbt build keeps human output on stdout",
        command_name="build",
        args=("--select", "tag:nightly"),
        expected_forwarded_args=("--select", "tag:nightly"),
        expected_progress_stream_name="stdout",
    ),
    DbtExecutionWrapperTestCase(
        description="dbt test strips local json and verbose flags before execution",
        command_name="test",
        args=("--json", "--verbose", "--select", "test_type:data"),
        expected_forwarded_args=("--select", "test_type:data"),
        expected_progress_stream_name="stderr",
    ),
]

DEBUG_WRAPPER_TEST_CASES: list[DbtDebugWrapperTestCase] = [
    DbtDebugWrapperTestCase(
        description="debug runs dbt then SQLBuild diagnostics and skips SQLBuild connection",
        args=("--project-dir", "dbt_project", "--no-connection"),
        expected_dbt_args=("--project-dir", "dbt_project", "--no-connection"),
        expected_sqlbuild_no_connection=True,
        expected_exit_code=0,
        expected_stderr_fragments=(
            "Running dbt debug...",
            "Running SQLBuild diagnostics...",
        ),
    ),
    DbtDebugWrapperTestCase(
        description="debug returns failure when dbt debug fails after SQLBuild diagnostics",
        args=(
            "--project-dir",
            "dbt_project",
        ),
        expected_dbt_args=("--project-dir", "dbt_project"),
        expected_sqlbuild_no_connection=False,
        expected_exit_code=1,
    ),
]

AUTO_INIT_NO_CREATE_TEST_CASES: list[DbtAutoInitTestCase] = [
    DbtAutoInitTestCase(
        description="uses current SQLBuild project when config exists",
        has_current_sqlbuild_project=True,
        has_sibling_sqlbuild_project=False,
        dbt_args=("--select", "orders"),
        expected_init_called=False,
        expected_forwarded_project_dir_name="dbt_project",
        expected_request_dbt_project_dir_name=None,
        expected_request_profiles_dir=None,
        expected_request_target_name=None,
    ),
    DbtAutoInitTestCase(
        description="uses existing sibling SQLBuild twin when current project is dbt",
        has_current_sqlbuild_project=False,
        has_sibling_sqlbuild_project=True,
        dbt_args=("--select", "orders"),
        expected_init_called=False,
        expected_forwarded_project_dir_name="sqlbuild_project",
        expected_request_dbt_project_dir_name=None,
        expected_request_profiles_dir=None,
        expected_request_target_name=None,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PROGRESS_TEST_CASES,
    ids=[case.description for case in PROGRESS_TEST_CASES],
)
def test_given_dbt_plan_when_running_then_writes_progress_to_expected_stream(
    test_case: DbtPlanProgressTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def plan_dbt_interop_from_project(
        *,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        progress_stream: object,
        use_color: bool,
    ) -> DbtInteropPlan:
        del project_dir, args, progress_stream, use_color
        assert callable(on_progress)
        on_progress("Compiling dbt project...")
        on_progress("Generated dbt interop plan. (0.01s)")
        return build_empty_dbt_plan()

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.plan_dbt_interop_from_project",
        plan_dbt_interop_from_project,
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.ensure_sqlbuild_project_for_dbt_command",
        lambda *, project_dir, args, no_color: (
            project_dir if project_dir is not None else Path.cwd(),
            args,
        ),
    )
    args: tuple[str, ...] = ("--json",) if test_case.json_output else ()

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand.PLAN,
        project_dir=Path("/project"),
        args=args,
        no_color=True,
    )

    captured: CaptureResult[str] = capsys.readouterr()
    assert exit_code == 0
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in captured.out
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in captured.err


@pytest.mark.parametrize(
    "test_case",
    EXECUTION_WRAPPER_TEST_CASES,
    ids=[case.description for case in EXECUTION_WRAPPER_TEST_CASES],
)
def test_given_dbt_execution_command_when_running_then_routes_expected_stream_and_args(
    test_case: DbtExecutionWrapperTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_calls: list[tuple[DbtInteropCommand, tuple[str, ...], object]] = []

    def execute_dbt_interop_from_project(
        *,
        command: DbtInteropCommand,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        progress_stream: object,
        dbt_stdout_stream: object,
        use_color: bool,
        verbose: bool,
        json_output: bool,
    ) -> int:
        del project_dir, on_progress, dbt_stdout_stream, use_color, verbose, json_output
        captured_calls.append((command, args, progress_stream))
        return 0

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.execute_dbt_interop_from_project",
        execute_dbt_interop_from_project,
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.ensure_sqlbuild_project_for_dbt_command",
        lambda *, project_dir, args, no_color: (
            project_dir if project_dir is not None else Path.cwd(),
            args,
        ),
    )

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand(test_case.command_name),
        project_dir=Path("/project"),
        args=test_case.args,
        no_color=True,
    )

    assert exit_code == 0
    assert captured_calls[0][1] == test_case.expected_forwarded_args
    expected_stream: object = (
        sys.stderr if test_case.expected_progress_stream_name == "stderr" else sys.stdout
    )
    assert captured_calls[0][2] is expected_stream


@pytest.mark.parametrize(
    "test_case",
    DEBUG_WRAPPER_TEST_CASES,
    ids=[case.description for case in DEBUG_WRAPPER_TEST_CASES],
)
def test_given_dbt_debug_command_when_running_then_invokes_dbt_and_sqlbuild_debug(
    test_case: DbtDebugWrapperTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dbt_calls: list[tuple[Path, tuple[str, ...], object, object]] = []
    sqlbuild_calls: list[tuple[Path | None, bool, bool, bool]] = []

    def debug_dbt_from_project(
        *,
        project_dir: Path,
        args: tuple[str, ...],
        stdout_stream: object,
        stderr_stream: object,
    ) -> int:
        dbt_calls.append((project_dir, args, stdout_stream, stderr_stream))
        return 1 if "fails" in test_case.description else 0

    def run_sqlbuild_debug(
        project_dir: Path | None,
        no_color: bool,
        no_connection: bool,
        json_output: bool,
    ) -> int:
        sqlbuild_calls.append((project_dir, no_color, no_connection, json_output))
        return 0

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt_debug.debug_dbt_from_project",
        debug_dbt_from_project,
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt_debug.run_sqlbuild_debug", run_sqlbuild_debug
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.ensure_sqlbuild_project_for_dbt_command",
        lambda *, project_dir, args, no_color: (
            project_dir if project_dir is not None else Path.cwd(),
            args,
        ),
    )

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand.DEBUG,
        project_dir=Path("/project"),
        args=test_case.args,
        no_color=True,
    )

    assert exit_code == test_case.expected_exit_code
    assert dbt_calls == [(Path("/project"), test_case.expected_dbt_args, sys.stdout, sys.stderr)]
    assert sqlbuild_calls == [
        (Path("/project"), True, test_case.expected_sqlbuild_no_connection, False)
    ]
    captured: CaptureResult[str] = capsys.readouterr()
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in captured.err


@pytest.mark.parametrize(
    "test_case",
    AUTO_INIT_NO_CREATE_TEST_CASES,
    ids=[case.description for case in AUTO_INIT_NO_CREATE_TEST_CASES],
)
def test_given_existing_sqlbuild_project_when_running_dbt_command_then_uses_expected_project(
    test_case: DbtAutoInitTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dbt_project_dir: Path = prepare_dbt_auto_init_dirs(test_case=test_case, tmp_path=tmp_path)
    forwarded_project_dirs: list[Path] = []
    init_requests: list[DbtInitRequest] = []

    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        init_requests.append(request)
        output_dir: Path | None = request.sqb_output_dir
        assert output_dir is not None
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "sqlbuild_project.toml").write_text(
            'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
        )
        return DbtInitResult(
            output_dir=output_dir,
            project_file=output_dir / "sqlbuild_project.toml",
            project_name="demo",
            macro_file=output_dir / "dbt" / "macros" / "generate_schema_name.sql",
            production_git_ref=request.production_git_ref,
            adapter="duckdb",
            target_name=request.target_name or "dev",
            profile_name="demo",
            toml='name = "demo"\n',
        )

    def plan_dbt_interop_from_project(
        *,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        progress_stream: object,
        use_color: bool,
    ) -> DbtInteropPlan:
        del args, on_progress, progress_stream, use_color
        forwarded_project_dirs.append(project_dir)
        return build_empty_dbt_plan()

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.helpers.dbt.auto_init.run_dbt_profile_init",
        run_dbt_profile_init,
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.plan_dbt_interop_from_project",
        plan_dbt_interop_from_project,
    )

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand.PLAN,
        project_dir=dbt_project_dir,
        args=test_case.dbt_args,
        no_color=True,
    )

    assert exit_code == 0
    assert forwarded_project_dirs[0].name == test_case.expected_forwarded_project_dir_name
    assert init_requests == []


@pytest.mark.parametrize(
    "test_case",
    [
        DbtAutoInitTestCase(
            description="creates sibling SQLBuild twin from typed dbt config flags",
            has_current_sqlbuild_project=False,
            has_sibling_sqlbuild_project=False,
            dbt_args=(
                "--project-dir",
                "dbt_project",
                "--profiles-dir",
                "profiles",
                "--target",
                "dev",
                "--select",
                "orders",
            ),
            expected_init_called=True,
            expected_forwarded_project_dir_name="sqlbuild_project",
            expected_request_dbt_project_dir_name="dbt_project",
            expected_request_profiles_dir="profiles",
            expected_request_target_name="dev",
        )
    ],
    ids=["creates sibling SQLBuild twin from typed dbt config flags"],
)
def test_given_missing_sqlbuild_twin_when_running_dbt_command_then_initializes_and_uses_twin(
    test_case: DbtAutoInitTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dbt_project_dir: Path = prepare_dbt_auto_init_dirs(test_case=test_case, tmp_path=tmp_path)
    forwarded_project_dirs: list[Path] = []
    forwarded_args: list[tuple[str, ...]] = []
    init_requests: list[DbtInitRequest] = []

    def run_dbt_profile_init(*, request: DbtInitRequest) -> DbtInitResult:
        init_requests.append(request)
        assert request.progress_callbacks.start is not None
        request.progress_callbacks.start("Inspecting dbt project and profile...")
        output_dir: Path | None = request.sqb_output_dir
        assert output_dir is not None
        output_dir.mkdir(parents=True, exist_ok=True)
        write_minimal_sqlbuild_project(output_dir)
        return DbtInitResult(
            output_dir=output_dir,
            project_file=output_dir / "sqlbuild_project.toml",
            project_name="demo",
            macro_file=output_dir / "dbt" / "macros" / "generate_schema_name.sql",
            production_git_ref=request.production_git_ref,
            adapter="duckdb",
            target_name=request.target_name or "dev",
            profile_name="demo",
            toml='name = "demo"\n',
        )

    def plan_dbt_interop_from_project(
        *,
        project_dir: Path,
        args: tuple[str, ...],
        on_progress: Callable[[str], None],
        progress_stream: object,
        use_color: bool,
    ) -> DbtInteropPlan:
        del on_progress, progress_stream, use_color
        forwarded_project_dirs.append(project_dir)
        forwarded_args.append(args)
        return build_empty_dbt_plan()

    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.helpers.dbt.auto_init.run_dbt_profile_init",
        run_dbt_profile_init,
    )
    monkeypatch.setattr(
        "sqlbuild.cli.commands.main.commands.dbt.plan_dbt_interop_from_project",
        plan_dbt_interop_from_project,
    )

    exit_code: int = run_dbt_command(
        command=DbtInteropCommand.PLAN,
        project_dir=dbt_project_dir,
        args=test_case.dbt_args,
        no_color=True,
    )

    assert exit_code == 0
    captured: CaptureResult[str] = capsys.readouterr()
    assert "Inspecting dbt project and profile..." in captured.err
    assert "SQLBuild dbt setup created" in captured.err
    assert "Production schema macro" in captured.err
    assert "not your dbt project" in captured.err
    assert "Inspecting dbt project and profile..." not in captured.out
    assert forwarded_project_dirs[0].name == test_case.expected_forwarded_project_dir_name
    assert Path(forwarded_args[0][forwarded_args[0].index("--project-dir") + 1]).is_absolute()
    assert Path(forwarded_args[0][forwarded_args[0].index("--profiles-dir") + 1]).is_absolute()
    assert bool(init_requests) is test_case.expected_init_called
    request: DbtInitRequest = init_requests[0]
    assert request.dbt_project_dir.name == test_case.expected_request_dbt_project_dir_name
    assert (
        None if request.profiles_dir is None else request.profiles_dir.as_posix()
    ) == test_case.expected_request_profiles_dir
    assert request.target_name == test_case.expected_request_target_name
    assert request.sqb_output_dir is not None
    assert request.sqb_output_dir.name == "sqlbuild_project"
    assert request.skip_dbt_debug is True
    assert request.production_git_ref == "main"
