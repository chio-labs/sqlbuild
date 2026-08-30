"""Deterministic virtual compile and planning timing tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker
from sqlbuild.diagnostics.models import PartialBuildPhaseTimings
from sqlbuild.virtual.executor._helpers import build as virtual_build_module
from sqlbuild.virtual.executor.models import VirtualBuildHooks, VirtualBuildOptions
from tests.unit.src.sqlbuild.virtual.executor._helpers._test_types import (
    VirtualPhaseTimingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPhaseTimingTestCase(
            description="slow virtual planning connection is excluded from compilation",
            clock_values=(0.0, 0.0, 2.0, 2.0, 12.0, 12.0),
            expected_compile_seconds=2.0,
            expected_planning_seconds=10.0,
            expected_total_seconds=12.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_slow_planning_connection_when_resolving_then_virtual_phases_are_disjoint(
    test_case: VirtualPhaseTimingTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic: Mock = Mock(side_effect=test_case.clock_values)
    graph: Mock = Mock()
    rewritten: Mock = Mock()
    plan: Mock = Mock()
    python_plan: Mock = Mock()
    monkeypatch.setattr(virtual_build_module.time, "monotonic", monotonic)
    monkeypatch.setattr(virtual_build_module, "build_project_graph", Mock(return_value=graph))
    monkeypatch.setattr(
        virtual_build_module, "_resolve_virtual_environment_names", Mock(return_value=Mock())
    )
    monkeypatch.setattr(
        virtual_build_module, "build_state_runtime", Mock(return_value=(Mock(), Mock()))
    )
    monkeypatch.setattr(
        virtual_build_module, "_read_virtual_build_state", Mock(return_value=Mock())
    )
    monkeypatch.setattr(
        virtual_build_module, "_rewrite_virtual_project", Mock(return_value=rewritten)
    )
    monkeypatch.setattr(virtual_build_module, "_plan_virtual_build", Mock(return_value=plan))
    monkeypatch.setattr(
        virtual_build_module, "_prepare_virtual_python_execution", Mock(return_value=python_plan)
    )
    tracker: BuildPhaseTimingTracker = BuildPhaseTimingTracker(monotonic=monotonic)

    with tracker.scope():
        resolution: virtual_build_module._VirtualBuildResolution = (
            virtual_build_module._resolve_virtual_build(
                project_dir=Mock(),
                discovered_inputs=Mock(),
                adapter=Mock(),
                connection_config={},
                options=VirtualBuildOptions(),
                hooks=VirtualBuildHooks(),
            )
        )
    timings: PartialBuildPhaseTimings = tracker.snapshot()

    assert resolution.compile_seconds == test_case.expected_compile_seconds
    assert resolution.planning_seconds == test_case.expected_planning_seconds
    assert timings.total_seconds == test_case.expected_total_seconds
    assert resolution.compile_seconds + resolution.planning_seconds <= (timings.total_seconds or 0)
