"""Deterministic compile and planning phase timing tests."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import Mock

import pytest

import sqlbuild._native as _native
from sqlbuild._native import (
    BuildPhaseTimingTracker,
    CompiledProject,
    CompilePipelineOptions,
    CompilePipelineResult,
    PartialBuildPhaseTimings,
    RulesRunResult,
    discover_project_inputs,
)
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.pipeline._helpers import materializations
from sqlbuild.runtime.contracts.models import ConnectionHooks
from tests.unit.src.sqlbuild.compiler.pipeline.main._test_types import PipelinePhaseTimingTestCase
from tests.unit.src.sqlbuild.compiler.pipeline.main.helpers import (
    ManualClock,
    SlowConnectionDuckDbAdapter,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PipelinePhaseTimingTestCase(
            description="slow planning connection is excluded from direct compilation",
            compile_seconds=2.0,
            connection_seconds=10.0,
            rules_seconds=0.0,
            expected_compile_seconds=2.0,
            expected_planning_seconds=10.0,
            expected_total_seconds=12.0,
        ),
        PipelinePhaseTimingTestCase(
            description="rules wall time is reported and excluded from compile and planning",
            compile_seconds=2.0,
            connection_seconds=10.0,
            rules_seconds=1.0,
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
    clock: ManualClock = ManualClock()
    project: CompiledProjectView = CompiledProject(
        run_id="timing-run",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
    )

    def compiled(**kwargs: object) -> CompiledProjectView:
        del kwargs
        clock.advance(test_case.compile_seconds)
        return project

    def evaluated(*args: object, **kwargs: object) -> RulesRunResult:
        del args, kwargs
        clock.advance(test_case.rules_seconds)
        return RulesRunResult(findings=(), evaluated_models=0, built_in_ms=0, custom_ms=0)

    monkeypatch.setattr(time, "monotonic", clock)
    monkeypatch.setattr(_native, "build_compiled_project", compiled)
    monkeypatch.setattr(materializations, "load_custom_materializations", Mock(return_value={}))
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "timing"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    monkeypatch.setattr(_native, "resolve_configured_rule_selection", Mock(return_value=None))
    monkeypatch.setattr(_native, "evaluate_rules", evaluated)
    tracker: BuildPhaseTimingTracker = BuildPhaseTimingTracker(monotonic=clock)
    progress: list[str] = []
    progress_hooks: dict[bool, ConnectionHooks] = {
        True: ConnectionHooks(on_progress=progress.append),
        False: ConnectionHooks(),
    }

    with tracker.scope():
        result: CompilePipelineResult = _native.run_compile_pipeline(
            discovered_inputs=discover_project_inputs(project_dir=tmp_path),
            adapter=SlowConnectionDuckDbAdapter(
                clock=clock, connection_seconds=test_case.connection_seconds
            ),
            options=CompilePipelineOptions(connection_config={}),
            hooks=progress_hooks[test_case.report_progress],
        )
    timings: PartialBuildPhaseTimings = tracker.snapshot()

    assert result.compile_seconds == test_case.expected_compile_seconds
    assert result.planning_seconds == test_case.expected_planning_seconds
    assert timings.total_seconds == test_case.expected_total_seconds
    assert (result.compile_seconds or 0) + (result.planning_seconds or 0) <= (
        timings.total_seconds or 0
    )
    assert set(test_case.expected_progress_fragments) <= set(progress)
