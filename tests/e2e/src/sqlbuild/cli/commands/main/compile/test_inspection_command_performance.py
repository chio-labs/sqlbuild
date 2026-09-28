"""Fresh-process speed and memory guards for read-only inspection commands.

The guarded project is the 3,000-model semantic benchmark plus a shared-dependency lattice: a hub
that fans out to eight models, sixteen layers where every slot joins two neighbouring slots of the
previous layer, and a rollup that fans the last layer back in. Graph walkers and tree renderers
that re-expand shared nodes per path blow up here exponentially, so their wall time, peak RSS and
output size are bounded against the project size.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    InspectionCommandPerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    INSPECTION_BENCHMARK_MODEL_COUNT,
    SHARED_DIAMOND_HUB,
    SHARED_DIAMOND_ROLLUP,
    InspectionCommandMeasurement,
    run_fresh_process_inspection_command,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)
_MIB: int = 1024 * 1024
_MODEL_COUNT: int = INSPECTION_BENCHMARK_MODEL_COUNT


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_lineage_text_downstream_from_fan_out_hub",
            sqb_args=("lineage", SHARED_DIAMOND_HUB, "--direction", "downstream"),
            expected_fragments=(
                f"Lineage  model  {SHARED_DIAMOND_HUB}",
                f"model  {SHARED_DIAMOND_ROLLUP}",
                "(already shown)",
            ),
            expected_max_output_lines=_MODEL_COUNT,
            expected_max_wall_seconds=2.5,
            expected_max_rss_bytes=128 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_lineage_text_upstream_from_fan_in_rollup",
            sqb_args=("lineage", SHARED_DIAMOND_ROLLUP, "--direction", "upstream"),
            expected_fragments=(
                f"Lineage  model  {SHARED_DIAMOND_ROLLUP}",
                f"model  {SHARED_DIAMOND_HUB}",
                "model  model_00000",
                "(already shown)",
            ),
            expected_max_output_lines=_MODEL_COUNT,
            expected_max_wall_seconds=2.5,
            expected_max_rss_bytes=128 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_lineage_json_downstream_from_fan_out_hub",
            sqb_args=(
                "lineage",
                SHARED_DIAMOND_HUB,
                "--direction",
                "downstream",
                "--format",
                "json",
            ),
            expected_fragments=(
                '"direction": "downstream"',
                f'"id": "model:{SHARED_DIAMOND_ROLLUP}"',
            ),
            expected_max_output_lines=20 * _MODEL_COUNT,
            expected_max_wall_seconds=2.5,
            expected_max_rss_bytes=128 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_lineage_json_upstream_from_fan_in_rollup",
            sqb_args=(
                "lineage",
                SHARED_DIAMOND_ROLLUP,
                "--direction",
                "upstream",
                "--format",
                "json",
            ),
            expected_fragments=(
                '"direction": "upstream"',
                f'"id": "model:{SHARED_DIAMOND_HUB}"',
                '"id": "model:model_00000"',
            ),
            expected_max_output_lines=20 * _MODEL_COUNT,
            expected_max_wall_seconds=2.5,
            expected_max_rss_bytes=128 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_dag_json",
            sqb_args=("dag", "--json"),
            expected_fragments=(
                '"project_name": "layered_production_performance_guard"',
                f'"id": "model:{SHARED_DIAMOND_ROLLUP}"',
            ),
            expected_max_output_lines=250 * _MODEL_COUNT,
            expected_max_wall_seconds=14.0,
            expected_max_rss_bytes=768 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_scope_json_for_fan_in_rollup",
            sqb_args=(
                "scope",
                f"model:{SHARED_DIAMOND_ROLLUP}",
                "--json",
                "--globals",
                "all",
                "--include-nearby",
            ),
            expected_fragments=(
                f'"identity":"model:{SHARED_DIAMOND_ROLLUP}"',
                '"complete":true',
            ),
            expected_max_output_lines=_MODEL_COUNT,
            expected_max_wall_seconds=2.5,
            expected_max_rss_bytes=144 * _MIB,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_shared_dependency_benchmark_when_inspecting_then_preserves_resource_budgets(
    inspection_benchmark_project: Path,
    test_case: InspectionCommandPerformanceGuardTestCase,
) -> None:
    result: InspectionCommandMeasurement = run_fresh_process_inspection_command(
        project_dir=inspection_benchmark_project,
        label=test_case.description,
        sqb_args=test_case.sqb_args,
        expected_max_wall_seconds=test_case.expected_max_wall_seconds,
    )
    output_lines: int = len(result.output.splitlines())
    _LOGGER.info(
        "inspection command %s wall=%.3fs cpu=%.3fs peak_rss_bytes=%d output_lines=%d",
        test_case.description,
        result.elapsed_seconds,
        result.cpu_seconds,
        result.peak_rss_bytes,
        output_lines,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in result.output
    assert output_lines <= test_case.expected_max_output_lines
    assert result.elapsed_seconds < test_case.expected_max_wall_seconds
    assert result.peak_rss_bytes < test_case.expected_max_rss_bytes
