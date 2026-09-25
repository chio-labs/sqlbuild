"""Bound the diagnostic-only paths missed by clean-project performance guards."""

import logging
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import pytest

from scripts.cold_compile_performance._helpers.diagnostic_measurement import (
    measure_diagnostic_compile,
    measure_position_mapping,
)
from scripts.cold_compile_performance._helpers.diagnostic_project import (
    write_cascade_project,
    write_diagnostic_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import DiagnosticPerformanceCase

_LOGGER: logging.Logger = logging.getLogger(__name__)
pytestmark: list[pytest.MarkDecorator] = [
    pytest.mark.performance,
    pytest.mark.cold_compile_performance,
]


@pytest.mark.parametrize(
    "test_case",
    [DiagnosticPerformanceCase("large_models_many_diagnostics")],
    ids=lambda case: case.description,
)
def test_given_large_invalid_models_when_compiling_then_bounds_diagnostic_work(
    test_case: DiagnosticPerformanceCase, tmp_path: Path
) -> None:
    write_diagnostic_project(project_dir=tmp_path, depth=test_case.depth, width=test_case.width)
    for path in (tmp_path / "models").glob("large_orders_*.sql"):
        assert len(path.read_text().splitlines()) >= 3000
    elapsed, payload = measure_diagnostic_compile(
        project_dir=tmp_path, timeout=test_case.expected_timeout_seconds
    )
    counts: Counter[tuple[str, str]] = Counter(
        (item.get("resource_name", ""), item["severity"]) for item in payload["diagnostics"]
    )
    for index in range(3):
        assert counts[(f"large_orders_{index}", "error")] >= 50
        assert counts[(f"large_orders_{index}", "warning")] >= 50
        assert f"downstream_orders_{index}" in payload["semantic_checks_partial"]
    _LOGGER.info("large diagnostic project wall=%.3fs counts=%s", elapsed, counts)
    assert elapsed < test_case.expected_max_wall_seconds


@pytest.mark.parametrize(
    "test_case",
    [DiagnosticPerformanceCase("mapping_scales_with_diagnostics", expected_max_wall_seconds=8.0)],
    ids=lambda case: case.description,
)
def test_given_many_spans_on_large_sql_when_mapping_then_scales_linearly(
    test_case: DiagnosticPerformanceCase,
) -> None:
    cold: float = measure_position_mapping(count=1)
    single: float = median(
        measure_position_mapping(count=test_case.diagnostic_count) for _ in range(3)
    )
    doubled: float = median(
        measure_position_mapping(count=test_case.diagnostic_count * 2) for _ in range(3)
    )
    _LOGGER.info("mapping cold=%.3fs N=%.3fs 2N=%.3fs", cold, single, doubled)
    assert cold + doubled < test_case.expected_max_wall_seconds
    assert doubled <= single * 2.8 + 0.1


@pytest.mark.parametrize(
    "test_case",
    [
        DiagnosticPerformanceCase(
            "deep_poisoned_dag", depth=40, width=50, expected_max_wall_seconds=35.0
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deep_poisoned_dag_when_recovering_then_bounds_scaling(
    test_case: DiagnosticPerformanceCase, tmp_path: Path
) -> None:
    timings: list[float] = []
    for multiplier in (1, 2):
        project: Path = tmp_path / f"depth_{multiplier}"
        write_cascade_project(
            project_dir=project, depth=test_case.depth * multiplier, width=test_case.width
        )
        elapsed, payload = measure_diagnostic_compile(
            project_dir=project, timeout=test_case.expected_max_wall_seconds + 5
        )
        diagnostics: list[dict[str, Any]] = payload["diagnostics"]
        assert len(diagnostics) == test_case.width
        assert all(item["code"] == "B212" for item in diagnostics)
        assert len(payload["semantic_checks_partial"]) == test_case.depth * multiplier + 1
        assert all(item.get("notes") for item in diagnostics)
        expected_note: str = f"{test_case.depth * multiplier} downstream output uses were not type-checked because of this error"
        for diagnostic in diagnostics:
            assert expected_note in diagnostic["notes"]
        timings.append(elapsed)
    _LOGGER.info("cascade depth=%d wall=%s", test_case.depth, timings)
    assert max(timings) < test_case.expected_max_wall_seconds
    assert timings[1] <= timings[0] * 3.0 + 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
