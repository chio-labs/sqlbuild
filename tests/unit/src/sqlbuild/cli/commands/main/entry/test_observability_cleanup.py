from __future__ import annotations

from contextvars import Token
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands._helpers.entry.observability import cli_observability_scope
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.observability import OperationLifecycle
from tests.unit.src.sqlbuild.cli.commands.main.entry._test_types import (
    MachineProgressRoutingCase,
    ObservabilityCleanupCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ObservabilityCleanupCase(
            description="projector close failure preserves original exception and cleanup",
            expected_history_close_count=1,
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
    history: Mock = Mock()
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
        with cli_observability_scope(
            args=args,
            project_dir=tmp_path,
            history_factory=lambda **_kwargs: history,
        ):
            assert current_native_progress_projector() is not outer
            raise ValueError(test_case.expected_original_error)

    assert current_native_progress_projector() is outer
    assert history.close.call_count == test_case.expected_history_close_count
    outer.restore(outer_token)


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
        ObservabilityCleanupCase(
            description="projector close failure preserves successful scope result",
            expected_history_close_count=1,
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
    history: Mock = Mock()

    with patch.object(
        NativeProgressProjector,
        "close",
        side_effect=OSError("controlled projector close failure"),
    ):
        with cli_observability_scope(
            args=args,
            project_dir=tmp_path,
            history_factory=lambda **_kwargs: history,
        ):
            result: str = "command result"

    assert result == "command result"
    assert test_case.expected_original_error == ""
    assert history.close.call_count == test_case.expected_history_close_count
