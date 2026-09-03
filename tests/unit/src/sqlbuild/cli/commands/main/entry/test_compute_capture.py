import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint import _dispatch_with_compute_logs as compute_dispatch
from sqlbuild.cli.commands.main.entrypoint.entry import _main_with_dependencies
from sqlbuild.cli.commands.models import CompileCommandRequest
from sqlbuild.diagnostics.classes.dynamic_stderr_handler import DynamicStderrHandler
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.diagnostics.main.log_sql import log_sql
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    CliCaptureOutcomeTestCase,
    MainTestCase,
    ProjectCreationRoutingTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.entry.helpers import build_handlers


@pytest.mark.parametrize(
    "test_case",
    (
        MainTestCase(
            description="successful compile has one complete invocation capture",
            argv=[],
            expected_exit_code=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_parsed_command_when_dispatch_completes_then_exact_compute_log_layout_is_published(
    tmp_path: Path,
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run_compile(_request: CompileCommandRequest) -> int:
        print("captured command output")
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=["--project-dir", str(tmp_path), "compile"],
        handlers=build_handlers(run_compile=run_compile),
    )
    captured: CaptureResult[str] = capsys.readouterr()
    capture_directories: tuple[Path, ...] = tuple((tmp_path / "logs").glob("*/*"))
    capture_dir: Path = capture_directories[0]
    metadata: dict[str, object] = json.loads(
        (capture_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert exit_code == test_case.expected_exit_code
    assert captured.out == "captured command output\n"
    assert {path.name for path in capture_dir.iterdir()} == {
        "stdout.log",
        "stderr.log",
        "diagnostics.jsonl",
        "metadata.json",
        "complete",
    }
    assert (capture_dir / "stdout.log").read_bytes() == b"captured command output\n"
    assert metadata["exit_code"] == test_case.expected_exit_code
    assert metadata["stdout_bytes"] == len(b"captured command output\n")


@pytest.mark.parametrize(
    "test_case",
    (
        CliCaptureOutcomeTestCase(
            description="expected command error is caught and capture completes",
            expected_exit_code=1,
            expected_complete=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_expected_command_error_when_cli_catches_then_failed_exit_capture_is_complete(
    tmp_path: Path, test_case: CliCaptureOutcomeTestCase
) -> None:
    def run_compile(_request: CompileCommandRequest) -> int:
        raise ValueError("controlled expected error")

    exit_code: int = _main_with_dependencies(
        argv=["--project-dir", str(tmp_path), "compile"],
        handlers=build_handlers(run_compile=run_compile),
    )
    capture_dir: Path = tuple((tmp_path / "logs").glob("*/*"))[0]
    metadata: dict[str, object] = json.loads(
        (capture_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert exit_code == test_case.expected_exit_code
    assert (capture_dir / "complete").exists() is test_case.expected_complete
    assert metadata["exit_code"] == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    (
        CliCaptureOutcomeTestCase(
            description="SystemExit is caught and capture records its code",
            expected_exit_code=9,
            expected_complete=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_system_exit_when_cli_catches_then_exit_code_and_complete_capture_are_preserved(
    tmp_path: Path, test_case: CliCaptureOutcomeTestCase
) -> None:
    def run_compile(_request: CompileCommandRequest) -> int:
        raise SystemExit(test_case.expected_exit_code)

    exit_code: int = _main_with_dependencies(
        argv=["--project-dir", str(tmp_path), "compile"],
        handlers=build_handlers(run_compile=run_compile),
    )
    capture_dir: Path = tuple((tmp_path / "logs").glob("*/*"))[0]
    metadata: dict[str, object] = json.loads(
        (capture_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert exit_code == test_case.expected_exit_code
    assert (capture_dir / "complete").exists() is test_case.expected_complete
    assert metadata["exit_code"] == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    (
        CliCaptureOutcomeTestCase(
            description="unexpected exception is re-raised after capture completion",
            expected_exit_code=1,
            expected_complete=True,
            expected_error_type=RuntimeError,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unexpected_exception_when_cli_does_not_catch_then_exception_and_capture_are_preserved(
    tmp_path: Path, test_case: CliCaptureOutcomeTestCase
) -> None:
    def run_compile(_request: CompileCommandRequest) -> int:
        logging.getLogger("sqlbuild.cli.plain").debug("plain internal before exception")
        raise RuntimeError("controlled unexpected error")

    with pytest.raises(RuntimeError, match="controlled unexpected error"):
        _ = _main_with_dependencies(
            argv=["--project-dir", str(tmp_path), "compile"],
            handlers=build_handlers(run_compile=run_compile),
        )
    capture_dir: Path = tuple((tmp_path / "logs").glob("*/*"))[0]
    metadata: dict[str, object] = json.loads(
        (capture_dir / "metadata.json").read_text(encoding="utf-8")
    )

    assert test_case.expected_error_type is RuntimeError
    assert (capture_dir / "complete").exists() is test_case.expected_complete
    assert metadata["exit_code"] == test_case.expected_exit_code
    diagnostics_text: str = (capture_dir / "diagnostics.jsonl").read_text(encoding="utf-8")
    assert diagnostics_text.count("plain internal before exception") == 1
    assert not (tmp_path / "target" / "sqlbuild.log").exists()


@pytest.mark.parametrize(
    "test_case",
    (
        MainTestCase(
            description="machine JSON stdout remains pure across every diagnostic family",
            argv=["compile", "--json"],
            expected_exit_code=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_machine_json_and_all_log_families_when_cli_runs_then_stdout_remains_parseable(
    tmp_path: Path,
    test_case: MainTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_sql: str = "SELECT 'cli-private-sql'"

    def run_compile(_request: CompileCommandRequest) -> int:
        logging.getLogger("sqlbuild.cli.matrix").debug("plain CLI internal")
        log_debug_event(
            logger=logging.getLogger("sqlbuild.cli.matrix"),
            message="structured CLI internal",
            sqlbuild_channel="cli_matrix",
        )
        user_logger: logging.Logger = logging.getLogger("project.cli")
        prior_level: int = user_logger.level
        user_logger.setLevel(logging.DEBUG)
        user_logger.debug("CLI user debug")
        user_logger.info("CLI user info")
        user_logger.setLevel(prior_level)
        log_sql(logger=logging.getLogger("sqlbuild.cli.matrix"), sql=private_sql)
        print(json.dumps({"status": "ok"}, separators=(",", ":")))
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=["--project-dir", str(tmp_path), *test_case.argv],
        handlers=build_handlers(run_compile=run_compile),
    )
    captured: CaptureResult[str] = capsys.readouterr()
    capture_dir: Path = tuple((tmp_path / "logs").glob("*/*"))[0]
    diagnostics_text: str = (capture_dir / "diagnostics.jsonl").read_text(encoding="utf-8")

    assert exit_code == test_case.expected_exit_code
    assert json.loads(captured.out) == {"status": "ok"}
    assert captured.err.count("CLI user info") == 1
    assert "plain CLI internal" not in captured.err
    assert "structured CLI internal" not in captured.err
    assert private_sql not in captured.err
    assert diagnostics_text.count("plain CLI internal") == 1
    assert diagnostics_text.count("structured CLI internal") == 1
    assert diagnostics_text.count("CLI user info") == 1
    assert "CLI user debug" not in diagnostics_text
    assert private_sql not in diagnostics_text
    assert not (tmp_path / "target" / "sqlbuild.log").exists()


@pytest.mark.parametrize(
    "test_case",
    (
        CliCaptureOutcomeTestCase(
            description="fallback routing reports capture failures and preserves operation return",
            expected_exit_code=17,
            expected_complete=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capture_and_cleanup_failures_when_handler_returns_then_reports_in_occurrence_order(
    tmp_path: Path,
    test_case: CliCaptureOutcomeTestCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage: Mock = Mock()
    storage.start_capture.side_effect = OSError("controlled capture open failure")
    storage.close.side_effect = OSError("controlled storage close failure")
    monkeypatch.setattr(
        compute_dispatch,
        "LocalFilesystemComputeLogStorage",
        Mock(return_value=storage),
    )

    with patch.object(
        DynamicStderrHandler,
        "close",
        Mock(side_effect=OSError("controlled route close failure")),
    ):
        exit_code: int = _main_with_dependencies(
            argv=["--debug", "--project-dir", str(tmp_path), "compile"],
            handlers=build_handlers(run_compile=Mock(return_value=test_case.expected_exit_code)),
        )

    stderr: str = capsys.readouterr().err
    failure_channels: list[object] = [record.__dict__["channel"] for record in caplog.records]
    assert exit_code == test_case.expected_exit_code
    assert stderr.count("local compute log capture unavailable") == 2
    assert failure_channels == ["capture_open", "capture_close"]
    assert not (tmp_path / "logs").exists()
    assert test_case.expected_complete is False


@pytest.mark.parametrize(
    "test_case",
    (
        CliCaptureOutcomeTestCase(
            description="fallback routing cleanup preserves operation exception",
            expected_exit_code=1,
            expected_complete=False,
            expected_error_type=RuntimeError,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capture_open_and_route_close_failures_when_handler_raises_then_error_is_preserved(
    tmp_path: Path, test_case: CliCaptureOutcomeTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        compute_dispatch,
        "LocalFilesystemComputeLogStorage",
        Mock(side_effect=OSError("controlled capture open failure")),
    )

    def raise_original(_request: CompileCommandRequest) -> int:
        raise RuntimeError("original fallback operation failure")

    with (
        patch.object(
            DynamicStderrHandler,
            "close",
            Mock(side_effect=OSError("controlled route close failure")),
        ),
        pytest.raises(RuntimeError, match="original fallback operation failure"),
    ):
        _ = _main_with_dependencies(
            argv=["--project-dir", str(tmp_path), "compile"],
            handlers=build_handlers(run_compile=raise_original),
        )

    assert not (tmp_path / "logs").exists()
    assert test_case.expected_error_type is RuntimeError
    assert test_case.expected_complete is False


@pytest.mark.parametrize(
    "test_case",
    (
        ProjectCreationRoutingTestCase(
            description="init bypasses project-local routes",
            argv=("init",),
            handler_name="run_init",
            expected_exit_code=21,
        ),
        ProjectCreationRoutingTestCase(
            description="playground bypasses project-local routes",
            argv=("playground", "shop"),
            handler_name="run_playground",
            expected_exit_code=22,
        ),
        ProjectCreationRoutingTestCase(
            description="dbt init bypasses project-local routes",
            argv=("dbt", "init", "--project-dir", "dbt-project"),
            handler_name="run_dbt_init",
            expected_exit_code=23,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_project_creation_command_when_handler_starts_then_no_project_routes_exist(
    tmp_path: Path, test_case: ProjectCreationRoutingTestCase
) -> None:
    def assert_pristine_routes(*_args: object, **_kwargs: object) -> int:
        assert not (tmp_path / "target").exists()
        assert not (tmp_path / "logs").exists()
        return test_case.expected_exit_code

    exit_code: int = _main_with_dependencies(
        argv=["--project-dir", str(tmp_path), *test_case.argv],
        handlers=build_handlers(**{test_case.handler_name: assert_pristine_routes}),
    )

    assert exit_code == test_case.expected_exit_code
    assert not (tmp_path / "target").exists()
    assert not (tmp_path / "logs").exists()
