from __future__ import annotations

import threading
from collections.abc import Callable
from contextvars import Token
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands._helpers.entry.observability import cli_observability_scope
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.output.constants import INTEGRATION_RESULT_PATH_ENV
from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.observability import OperationLifecycle
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    MachineProgressRoutingCase,
    NoExporterFastPathTestCase,
    ObservabilityCleanupCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ObservabilityCleanupCase(
            description="projector close failure preserves original exception and cleanup",
            expected_original_error="original command failure",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_projector_close_failure_when_command_fails_then_original_error_and_cleanup_survive(
    tmp_path: Path,
    test_case: ObservabilityCleanupCase,
) -> None:
    args: CliNamespace = CliNamespace()
    outer: NativeProgressProjector = NativeProgressProjector(stream=StringIO(), use_color=False)
    outer_token: Token[NativeProgressProjector | None] = outer.install()

    with (
        patch.object(
            NativeProgressProjector,
            "close",
            side_effect=OSError("controlled projector close failure"),
        ),
        pytest.raises(ValueError, match=test_case.expected_original_error),
    ):
        with cli_observability_scope(args=args, project_dir=tmp_path):
            assert current_native_progress_projector() is not outer
            raise ValueError(test_case.expected_original_error)

    assert current_native_progress_projector() is outer
    outer.restore(outer_token)


@pytest.mark.parametrize(
    "test_case",
    (NoExporterFastPathTestCase("no public exporter skips providers and thread", 0),),
    ids=lambda case: case.description,
)
def test_given_no_public_exporter_when_observability_runs_then_provider_import_is_skipped(
    test_case: NoExporterFastPathTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    marker_path: Path = tmp_path / "provider-imported"
    helper_marker_path: Path = tmp_path / "helper-imported"
    write_repo_files(
        tmp_path,
        {
            "providers/exploding.py": (
                "from pathlib import Path\n"
                f"Path({str(marker_path)!r}).write_text('imported', encoding='utf-8')\n"
                "raise RuntimeError('provider must not import')\n"
            ),
            "event_exporters/_private.py": "raise RuntimeError('private exporter imported')\n",
            "event_exporters/helpers.py": (
                "from pathlib import Path\n"
                f"Path({str(helper_marker_path)!r}).write_text('imported', encoding='utf-8')\n"
                "def encode(value):\n    return value\n"
            ),
        },
    )
    args: CliNamespace = CliNamespace()
    before_threads: int = sum(
        map(
            lambda thread: thread.name.startswith("sqlbuild-event-exporter-"),
            threading.enumerate(),
        )
    )

    with cli_observability_scope(args=args, project_dir=tmp_path):
        with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
            pass
        active_threads: int = sum(
            map(
                lambda thread: thread.name.startswith("sqlbuild-event-exporter-"),
                threading.enumerate(),
            )
        )

    assert not marker_path.exists()
    assert helper_marker_path.exists()
    assert active_threads - before_threads == test_case.expected_thread_delta


@pytest.mark.parametrize(
    "test_case",
    (
        MachineProgressRoutingCase(
            description="json output file retains human stdout progress",
            json=False,
            json_output=Path("target/result.json"),
            expected_stdout_fragment="Project compile  START",
            expected_stderr_fragment="",
        ),
        MachineProgressRoutingCase(
            description="json mode routes human progress to stderr",
            json=True,
            json_output=None,
            expected_stdout_fragment="",
            expected_stderr_fragment="Project compile  START",
        ),
        MachineProgressRoutingCase(
            description="json mode with output file still routes progress to stderr",
            json=True,
            json_output=Path("target/result.json"),
            expected_stdout_fragment="",
            expected_stderr_fragment="Project compile  START",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_json_routing_options_when_operation_runs_then_human_stream_contract_is_preserved(
    tmp_path: Path,
    test_case: MachineProgressRoutingCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args: CliNamespace = CliNamespace()
    args.json = test_case.json
    args.json_output = test_case.json_output

    with cli_observability_scope(args=args, project_dir=tmp_path):
        with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
            pass

    captured: CaptureResult[str] = capsys.readouterr()
    assert test_case.expected_stdout_fragment in captured.out
    assert test_case.expected_stderr_fragment in captured.err


@pytest.mark.parametrize(
    "test_case",
    (
        MachineProgressRoutingCase(
            description="integration result file retains human stdout progress",
            json=False,
            json_output=None,
            expected_stdout_fragment="Project compile  START",
            expected_stderr_fragment="",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_integration_result_file_when_operation_runs_then_human_progress_uses_stdout(
    tmp_path: Path,
    test_case: MachineProgressRoutingCase,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args: CliNamespace = CliNamespace()
    args.event_output = tmp_path / "events.jsonl"
    monkeypatch.setenv(INTEGRATION_RESULT_PATH_ENV, str(tmp_path / "integration.jsonl"))

    with cli_observability_scope(args=args, project_dir=tmp_path):
        with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
            pass

    captured: CaptureResult[str] = capsys.readouterr()
    assert test_case.expected_stdout_fragment in captured.out
    assert captured.err == test_case.expected_stderr_fragment


@pytest.mark.parametrize(
    "test_case",
    (
        ObservabilityCleanupCase(
            description="projector close failure preserves successful scope result",
            expected_original_error="",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_projector_close_failure_when_scope_succeeds_then_cleanup_does_not_raise(
    tmp_path: Path,
    test_case: ObservabilityCleanupCase,
) -> None:
    args: CliNamespace = CliNamespace()

    with patch.object(
        NativeProgressProjector,
        "close",
        side_effect=OSError("controlled projector close failure"),
    ):
        with cli_observability_scope(args=args, project_dir=tmp_path):
            result: str = "command result"

    assert result == "command result"
    assert test_case.expected_original_error == ""
