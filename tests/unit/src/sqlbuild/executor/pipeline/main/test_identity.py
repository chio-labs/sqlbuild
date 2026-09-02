from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

import sqlbuild.executor.pipeline.main.run as run_module
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.models import CostResourceContext
from sqlbuild.executor.build.models import BuildExecutionResult, BuildRuntimeParams
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.observability import ExecutionIdentity, current_execution_identity, invocation_scope
from sqlbuild.spec.contracts.models import SettingsConfig
from tests.unit.src.sqlbuild.executor.pipeline.main._test_types import PipelineIdentityTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        PipelineIdentityTestCase(
            description="shared run boundary preserves SQLBuild run ID and outer invocation",
            expected_invocation_id="inv-outer",
            expected_run_id="SQLBuild Run / 001",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_outer_invocation_when_running_shared_pipeline_then_run_and_cost_contexts_are_scoped(
    test_case: PipelineIdentityTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_identities: list[ExecutionIdentity | None] = []
    observed_cost_contexts: list[CostResourceContext | None] = []
    expected_result: BuildExecutionResult = BuildExecutionResult(status=BuildStatus.SUCCESS)

    def execute_pipeline(**_kwargs: Any) -> BuildExecutionResult:
        observed_identities.append(current_execution_identity())
        observed_cost_contexts.append(CostContext.current())
        return expected_result

    monkeypatch.setattr(run_module, "_run_build_pipeline", execute_pipeline)
    runtime: BuildRuntimeParams = BuildRuntimeParams(
        run_id=test_case.expected_run_id,
        runtime_dir=Path("target"),
        target="dev",
    )

    with invocation_scope(test_case.expected_invocation_id) as outer:
        result: BuildExecutionResult = run_module.run_build_pipeline(
            plan=PlanOutput(),
            connection_config={},
            adapter=Mock(spec=BaseAdapter),
            settings=Mock(spec=SettingsConfig),
            runtime=runtime,
        )
        restored: ExecutionIdentity | None = current_execution_identity()

    assert result == expected_result
    assert observed_identities[0] is not None
    assert observed_identities[0].invocation_id == test_case.expected_invocation_id
    assert observed_identities[0].run_id == test_case.expected_run_id
    assert observed_cost_contexts[0] is not None
    assert observed_cost_contexts[0].run_id == test_case.expected_run_id
    assert restored == outer
    assert current_execution_identity() is None
