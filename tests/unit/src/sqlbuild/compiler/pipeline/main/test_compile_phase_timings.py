"""Deterministic compile and planning phase timing tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.pipeline.main import compile as compile_module
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker
from sqlbuild.diagnostics.models import PartialBuildPhaseTimings
from tests.unit.src.sqlbuild.compiler.pipeline.main._test_types import PipelinePhaseTimingTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        PipelinePhaseTimingTestCase(
            description="slow planning connection is excluded from direct compilation",
            clock_values=(0.0, 0.0, 2.0, 2.0, 12.0, 12.0),
            expected_compile_seconds=2.0,
            expected_planning_seconds=10.0,
            expected_total_seconds=12.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_slow_planning_connection_when_compiling_then_direct_phases_are_disjoint(
    test_case: PipelinePhaseTimingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic: Mock = Mock(side_effect=test_case.clock_values)
    project: CompiledProject = CompiledProject(
        run_id="timing-run",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
    )
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=project, plan_output=PlanOutput()
    )
    adapter: Mock = Mock()
    monkeypatch.setattr(compile_module.time, "monotonic", monotonic)
    monkeypatch.setattr(compile_module, "build_compiled_project", Mock(return_value=project))
    monkeypatch.setattr(
        compile_module, "resolve_compile_analysis_selection", Mock(return_value=None)
    )
    monkeypatch.setattr(compile_module, "open_connection_with_hooks", Mock(return_value=object()))
    monkeypatch.setattr(compile_module, "_build_result", Mock(return_value=pipeline_result))
    tracker: BuildPhaseTimingTracker = BuildPhaseTimingTracker(monotonic=monotonic)

    with tracker.scope():
        result: CompilePipelineResult = compile_module.run_compile_pipeline(
            discovered_inputs=Mock(),
            adapter=adapter,
            options=CompilePipelineOptions(connection_config={}),
        )
    timings: PartialBuildPhaseTimings = tracker.snapshot()

    assert result.compile_seconds == test_case.expected_compile_seconds
    assert result.planning_seconds == test_case.expected_planning_seconds
    assert timings.total_seconds == test_case.expected_total_seconds
    assert (result.compile_seconds or 0) + (result.planning_seconds or 0) <= (
        timings.total_seconds or 0
    )
