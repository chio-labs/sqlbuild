"""Tests for per-phase medians in the same-runner compile performance ratio guard."""

import pytest

from scripts.compile_performance_ratio._helpers.measure import median_phases
from scripts.compile_performance_ratio.models import CompileRun
from tests.unit.scripts.compile_performance_ratio._helpers._test_types import (
    MedianPhasesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        MedianPhasesTestCase(
            description="a phase every run reports gets its median",
            runs=(
                CompileRun(
                    label="head",
                    wall_seconds=1.0,
                    cpu_seconds=1.0,
                    timings_ms={"contracts_cpu_ms": 90},
                ),
                CompileRun(
                    label="head",
                    wall_seconds=1.0,
                    cpu_seconds=1.0,
                    timings_ms={"contracts_cpu_ms": 120},
                ),
                CompileRun(
                    label="head",
                    wall_seconds=1.0,
                    cpu_seconds=1.0,
                    timings_ms={"contracts_cpu_ms": 100},
                ),
            ),
            expected_phases={"contracts_cpu_ms": 100},
        ),
        MedianPhasesTestCase(
            description="a phase one run omits is left unreported instead of counted as zero",
            runs=(
                CompileRun(
                    label="head",
                    wall_seconds=1.0,
                    cpu_seconds=1.0,
                    timings_ms={"contracts_cpu_ms": 90},
                ),
                CompileRun(label="head", wall_seconds=1.0, cpu_seconds=1.0, timings_ms={}),
            ),
            expected_phases={},
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_compile_runs_when_taking_phase_medians_then_reports_only_complete_phases(
    test_case: MedianPhasesTestCase,
) -> None:
    assert median_phases(runs=list(test_case.runs)) == test_case.expected_phases
