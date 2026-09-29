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
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    InspectionCommandPerformanceGuardTestCase,
    PlanComparedToCompileGuardTestCase,
    PlanScalingGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    INSPECTION_BENCHMARK_MODEL_COUNT,
    SHARED_DIAMOND_HUB,
    SHARED_DIAMOND_ROLLUP,
    InspectionCommandMeasurement,
    prepare_small_inspection_project,
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
            expected_max_wall_seconds=3.0,
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
            expected_max_wall_seconds=3.0,
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
            expected_max_wall_seconds=3.0,
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
            expected_max_wall_seconds=3.0,
            expected_max_rss_bytes=128 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_lineage_column_text_upstream_from_fan_in_rollup",
            sqb_args=("lineage", f"{SHARED_DIAMOND_ROLLUP}.amount", "--direction", "upstream"),
            expected_fragments=(
                f"Column trace  {SHARED_DIAMOND_ROLLUP}.amount  upstream",
                "shared_orders_l15_s00.amount (cast)",
            ),
            expected_max_output_lines=_MODEL_COUNT,
            expected_max_wall_seconds=8.0,
            expected_max_rss_bytes=512 * _MIB,
        ),
        InspectionCommandPerformanceGuardTestCase(
            description="models_3000_lineage_column_json_downstream_from_fan_out_hub",
            sqb_args=(
                "lineage",
                f"{SHARED_DIAMOND_HUB}.amount",
                "--direction",
                "downstream",
                "--format",
                "json",
            ),
            expected_fragments=(
                '"direction": "downstream"',
                f'"resource_name": "{SHARED_DIAMOND_ROLLUP}"',
            ),
            expected_max_output_lines=20 * _MODEL_COUNT,
            expected_max_wall_seconds=8.0,
            expected_max_rss_bytes=512 * _MIB,
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


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        PlanComparedToCompileGuardTestCase(
            description="models_3000_plan_json_relative_to_warm_compile",
            expected_max_compile_ratio=2.6,
            expected_max_plan_wall_seconds=45.0,
            expected_max_rss_bytes=1_280 * _MIB,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shared_dependency_benchmark_when_planning_then_stays_near_compile(
    inspection_benchmark_project: Path,
    test_case: PlanComparedToCompileGuardTestCase,
) -> None:
    compiled: InspectionCommandMeasurement = run_fresh_process_inspection_command(
        project_dir=inspection_benchmark_project,
        label=f"{test_case.description}-compile",
        sqb_args=("compile", "--json"),
        expected_max_wall_seconds=test_case.expected_max_plan_wall_seconds,
    )

    planned: InspectionCommandMeasurement = run_fresh_process_inspection_command(
        project_dir=inspection_benchmark_project,
        label=test_case.description,
        sqb_args=("plan", "--json"),
        expected_max_wall_seconds=test_case.expected_max_plan_wall_seconds,
    )

    ratio: float = planned.elapsed_seconds / compiled.elapsed_seconds
    _LOGGER.info(
        "plan %s wall=%.3fs cpu=%.3fs peak_rss_bytes=%d compile_wall=%.3fs ratio=%.2f",
        test_case.description,
        planned.elapsed_seconds,
        planned.cpu_seconds,
        planned.peak_rss_bytes,
        compiled.elapsed_seconds,
        ratio,
    )
    assert len(cast(dict[str, list[object]], planned.payload)["models"]) == _MODEL_COUNT
    assert ratio < test_case.expected_max_compile_ratio
    assert planned.peak_rss_bytes < test_case.expected_max_rss_bytes


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        PlanScalingGuardTestCase(
            description="models_3000_plan_work_scales_linearly_from_300_models",
            small_model_count=300,
            expected_max_linear_factor=2.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_benchmarks_of_two_sizes_when_planning_then_planning_work_scales_linearly(
    inspection_benchmark_project: Path,
    test_case: PlanScalingGuardTestCase,
    tmp_path: Path,
) -> None:
    small_project: Path = tmp_path / "semantic_small"
    prepare_small_inspection_project(
        project_dir=small_project, model_count=test_case.small_model_count
    )
    planning_cpu: dict[str, float] = {}
    label: str
    project_dir: Path
    for label, project_dir in (("small", small_project), ("large", inspection_benchmark_project)):
        compiled: InspectionCommandMeasurement = run_fresh_process_inspection_command(
            project_dir=project_dir,
            label=f"{test_case.description}-{label}-compile",
            sqb_args=("compile", "--json"),
            expected_max_wall_seconds=60.0,
        )
        planned: InspectionCommandMeasurement = run_fresh_process_inspection_command(
            project_dir=project_dir,
            label=f"{test_case.description}-{label}-plan",
            sqb_args=("plan", "--json"),
            expected_max_wall_seconds=60.0,
        )
        planning_cpu[label] = planned.cpu_seconds - compiled.cpu_seconds

    linear_cpu: float = planning_cpu["small"] * _MODEL_COUNT / test_case.small_model_count
    _LOGGER.info(
        "plan scaling %s small_planning_cpu=%.3fs large_planning_cpu=%.3fs linear=%.3fs",
        test_case.description,
        planning_cpu["small"],
        planning_cpu["large"],
        linear_cpu,
    )
    assert planning_cpu["large"] < test_case.expected_max_linear_factor * linear_cpu
