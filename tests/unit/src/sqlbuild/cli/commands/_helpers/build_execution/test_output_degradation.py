"""Post-execution output degradation boundary tests."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from sqlbuild.cli.commands._helpers.build_execution import outputs
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildExecutionPreparation,
    BuildInvocation,
    BuildRunOutcome,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from tests.unit.src.sqlbuild.cli.commands._helpers.build_execution._test_types import (
    ExecutionProjectionFailureTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ExecutionProjectionFailureTestCase(
            description="successful execution projection failure",
            build_status="success",
            expected_exit_code=0,
            expected_document_status="success",
            expected_completion_message="warehouse execution completed successfully",
        ),
        ExecutionProjectionFailureTestCase(
            description="failed execution projection failure",
            build_status="failed",
            expected_exit_code=1,
            expected_document_status="failed",
            expected_completion_message="execution result remains authoritative",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_completed_execution_when_json_projection_fails_then_exit_status_remains_authoritative(
    test_case: ExecutionProjectionFailureTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path: Path = tmp_path / "execution.json"
    outcome: BuildRunOutcome = BuildRunOutcome(
        result=BuildExecutionResult(status=BuildStatus(test_case.build_status)),
        python_results=(),
    )
    monkeypatch.setattr(outputs, "format_build_footer", Mock(return_value="completed"))
    monkeypatch.setattr(
        outputs,
        "format_build_execution_json",
        Mock(side_effect=ObservabilityValidationError("injected projection failure")),
    )

    outputs.write_build_completion_output(
        request=cast(
            BuildCommandRequest,
            SimpleNamespace(json_output=False, json_output_path=output_path),
        ),
        invocation=cast(
            BuildInvocation,
            SimpleNamespace(use_color=False, progress_stream=StringIO()),
        ),
        pipeline_result=cast(
            CompilePipelineResult,
            SimpleNamespace(plan_output=Mock(), project=Mock()),
        ),
        preparation=cast(
            BuildExecutionPreparation,
            SimpleNamespace(callbacks=SimpleNamespace(elapsed=1.0)),
        ),
        outcome=outcome,
        check_results=(),
    )

    payload: dict[str, object] = json.loads(output_path.read_text(encoding="utf-8"))
    assert outputs.resolve_build_exit_code(outcome=outcome, check_results=()) == (
        test_case.expected_exit_code
    )
    assert payload["status"] == test_case.expected_document_status
    assert payload["projection_degraded"] is True
    assert test_case.expected_completion_message in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
