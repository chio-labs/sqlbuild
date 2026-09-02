import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import _main_with_dependencies
from sqlbuild.cli.commands.models import CompileCommandRequest
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    CliCaptureOutcomeTestCase,
    MainTestCase,
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
