"""Virtual-build post-execution output degradation tests."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.execution import _virtual_build
from sqlbuild.cli.commands.models import VirtualBuildCliRequest, VirtualBuildExecution
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult
from tests.unit.src.sqlbuild.cli.commands.main.execution._test_types import (
    VirtualBuildProjectionFailureTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildProjectionFailureTestCase(
            description="successful virtual execution projection failure",
            build_status="success",
            expected_exit_code=0,
            expected_document_status="success",
            expected_completion_message="warehouse execution completed successfully",
        ),
        VirtualBuildProjectionFailureTestCase(
            description="failed virtual execution projection failure",
            build_status="failed",
            expected_exit_code=1,
            expected_document_status="failed",
            expected_completion_message="execution result remains authoritative",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_completed_virtual_execution_when_projection_fails_then_exit_status_is_preserved(
    test_case: VirtualBuildProjectionFailureTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path: Path = tmp_path / "execution.json"
    result: VirtualBuildPipelineResult = cast(
        VirtualBuildPipelineResult,
        SimpleNamespace(
            display_plan_output=Mock(),
            python_node_results=(),
            execution_result=BuildExecutionResult(status=BuildStatus(test_case.build_status)),
            execution_plan=Mock(),
            project=SimpleNamespace(
                run_id="run-1",
                effective_target_name="dev",
                effective_target_database="warehouse",
            ),
        ),
    )
    request: VirtualBuildCliRequest = cast(
        VirtualBuildCliRequest,
        SimpleNamespace(
            exclude=(),
            reload_sources=False,
            providers=(),
            use_color=False,
            execution_command="build",
            json_output=False,
            json_output_path=output_path,
        ),
    )
    monkeypatch.setattr(_virtual_build, "write_python_node_results", Mock())
    monkeypatch.setattr(_virtual_build.CostContext, "scope", Mock(return_value=nullcontext()))
    monkeypatch.setattr(_virtual_build, "run_post_virtual_build_checks", Mock(return_value=()))
    monkeypatch.setattr(_virtual_build, "format_build_footer", Mock(return_value="completed"))
    monkeypatch.setattr(_virtual_build, "write_runtime_target", Mock())
    monkeypatch.setattr(_virtual_build, "write_python_check_runtime_target", Mock())
    monkeypatch.setattr(_virtual_build, "plan_has_executable_work", Mock(return_value=False))
    monkeypatch.setattr(_virtual_build, "finalize_build_cost", Mock(return_value=None))
    monkeypatch.setattr(
        "sqlbuild.cli.commands._helpers.build_execution.outputs.format_build_execution_json",
        Mock(side_effect=ObservabilityValidationError("injected projection failure")),
    )
    monkeypatch.setattr(_virtual_build, "render_build_cost", Mock())
    monkeypatch.setattr(_virtual_build, "record_and_write_virtual_build_phase_timings", Mock())

    exit_code: int = _virtual_build._complete_virtual_build(
        project_dir=tmp_path,
        discovered_inputs=cast(
            DiscoveredProjectInputs,
            SimpleNamespace(project_config=SimpleNamespace(cost=Mock())),
        ),
        adapter=cast(BaseAdapter, Mock()),
        adapter_name="duckdb",
        connection_config={},
        request=request,
        execution=cast(VirtualBuildExecution, SimpleNamespace(elapsed=1.0)),
        result=result,
        stream=StringIO(),
        build_started_at=datetime.now(UTC),
    )

    payload: dict[str, object] = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == test_case.expected_exit_code
    assert payload["status"] == test_case.expected_document_status
    assert payload["projection_degraded"] is True
    assert test_case.expected_completion_message in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
