"""Deterministic compile and planning phase timing tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock

import pytest

import sqlbuild._native as _native
from sqlbuild._native import BuildPhaseTimingTracker, PartialBuildPhaseTimings
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.pipeline._helpers import materializations
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.rule_engine.models import RulesRunResult
from sqlbuild.runtime.contracts.models import ConnectionHooks
from tests.unit.src.sqlbuild.compiler.pipeline.main._test_types import PipelinePhaseTimingTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        PipelinePhaseTimingTestCase(
            description="slow planning connection is excluded from direct compilation",
            clock_values=(0.0, 0.0, 2.0, 2.0, 3.0, 3.0, 13.0, 13.0),
            expected_compile_seconds=2.0,
            expected_planning_seconds=10.0,
            expected_total_seconds=13.0,
        ),
        PipelinePhaseTimingTestCase(
            description="rules wall time is reported and excluded from compile and planning",
            clock_values=(0.0, 0.0, 2.0, 2.0, 3.0, 3.0, 3.0, 13.0, 13.0),
            expected_compile_seconds=2.0,
            expected_planning_seconds=10.0,
            expected_total_seconds=13.0,
            report_progress=True,
            expected_progress_fragments=(
                "Compiled project. (2.00s)",
                "Evaluated rules. (1.00s; built-in 0.00s, custom 0.00s)",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_slow_planning_connection_when_compiling_then_direct_phases_are_disjoint(
    test_case: PipelinePhaseTimingTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monotonic: Mock = Mock(side_effect=test_case.clock_values)
    project: CompiledProjectView = CompiledProject(
        run_id="timing-run",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
    )
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=project, plan_output=PlanOutput()
    )
    adapter: Mock = Mock()
    monkeypatch.setattr(time, "monotonic", monotonic)
    monkeypatch.setattr(_native, "build_compiled_project", Mock(return_value=project))
    monkeypatch.setattr(_native, "build_execution_plan", Mock(return_value=PlanOutput()))
    monkeypatch.setattr(materializations, "load_custom_materializations", Mock(return_value={}))
    monkeypatch.setattr(
        _native,
        "build_python_run_plan_outputs",
        Mock(
            return_value=Mock(
                plan_output=pipeline_result.plan_output,
                selected_python_node_names=frozenset(),
                python_plan_entries=(),
            )
        ),
    )
    (tmp_path / "sqlbuild_project.toml").write_text('name = "timing"\n', encoding="utf-8")
    monkeypatch.setattr(_native, "resolve_configured_rule_selection", Mock(return_value=None))
    monkeypatch.setattr(
        _native,
        "evaluate_rules",
        Mock(
            return_value=RulesRunResult(findings=(), evaluated_models=0, built_in_ms=0, custom_ms=0)
        ),
    )
    tracker: BuildPhaseTimingTracker = BuildPhaseTimingTracker(monotonic=monotonic)
    progress: list[str] = []
    progress_hooks: dict[bool, ConnectionHooks] = {
        True: ConnectionHooks(on_progress=progress.append),
        False: ConnectionHooks(),
    }

    with tracker.scope():
        result: CompilePipelineResult = _native.run_compile_pipeline(
            discovered_inputs=Mock(project_dir=tmp_path),
            adapter=adapter,
            options=CompilePipelineOptions(connection_config={}),
            hooks=progress_hooks[test_case.report_progress],
        )
    timings: PartialBuildPhaseTimings = tracker.snapshot()

    assert result.compile_seconds == test_case.expected_compile_seconds
    assert result.planning_seconds == test_case.expected_planning_seconds
    assert timings.total_seconds == test_case.expected_total_seconds
    assert (result.compile_seconds or 0) + (result.planning_seconds or 0) < (
        timings.total_seconds or 0
    )
    assert set(test_case.expected_progress_fragments) <= set(progress)
