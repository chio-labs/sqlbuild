"""Fresh-process speed and memory guards for sqb build and planning against existing state.

The guarded project is a 1,000-model DuckDB benchmark without tests or audits. It is built once
from an empty warehouse; later cases copy the built project, change a few models or rename one,
and plan again so change detection and rename discovery run against real stored state.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    BuildPerformanceGuardTestCase,
    ExistingStatePlanGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    BuiltBenchmark,
    InspectionCommandMeasurement,
    change_benchmark_models,
    plan_reasons_and_migrations,
    run_fresh_process_inspection_command,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)
_MIB: int = 1024 * 1024


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        BuildPerformanceGuardTestCase(
            description="models_3000_job_build_1000_model_benchmark_from_empty_warehouse",
            expected_max_wall_seconds=90.0,
            expected_max_rss_bytes=1_600 * _MIB,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_empty_warehouse_when_building_benchmark_then_preserves_resource_budgets(
    built_benchmark: BuiltBenchmark, test_case: BuildPerformanceGuardTestCase
) -> None:
    build: InspectionCommandMeasurement = built_benchmark.build
    _LOGGER.info(
        "build %s wall=%.3fs cpu=%.3fs peak_rss_bytes=%d",
        test_case.description,
        build.elapsed_seconds,
        build.cpu_seconds,
        build.peak_rss_bytes,
    )

    assert "Completed successfully" in build.output
    assert build.elapsed_seconds < test_case.expected_max_wall_seconds
    assert build.peak_rss_bytes < test_case.expected_max_rss_bytes


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        ExistingStatePlanGuardTestCase(
            description="models_3000_job_plan_after_editing_three_built_models",
            edited_models=("model_00994", "model_00995", "model_00996"),
            renamed_models=(),
            expected_query_changed=("model_00994", "model_00995", "model_00996"),
            expected_migrations=(),
            expected_max_wall_seconds=9.0,
            expected_max_rss_bytes=768 * _MIB,
        ),
        ExistingStatePlanGuardTestCase(
            description="models_3000_job_plan_after_editing_and_renaming_built_models",
            edited_models=("model_00994",),
            renamed_models=(("model_00999", "model_00999_renamed"),),
            expected_query_changed=("model_00994",),
            expected_migrations=(("model_00999", "model_00999_renamed", "renamed"),),
            expected_max_wall_seconds=9.0,
            expected_max_rss_bytes=768 * _MIB,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_built_benchmark_when_models_change_then_plan_preserves_resource_budgets(
    built_benchmark: BuiltBenchmark,
    test_case: ExistingStatePlanGuardTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "semantic_build"
    _ = shutil.copytree(built_benchmark.project_dir, project_dir)
    change_benchmark_models(
        project_dir=project_dir,
        edited_models=test_case.edited_models,
        renamed_models=test_case.renamed_models,
    )

    plan: InspectionCommandMeasurement = run_fresh_process_inspection_command(
        project_dir=project_dir,
        label=test_case.description,
        sqb_args=("plan", "--json"),
        expected_max_wall_seconds=test_case.expected_max_wall_seconds,
    )

    _LOGGER.info(
        "existing-state plan %s wall=%.3fs cpu=%.3fs peak_rss_bytes=%d",
        test_case.description,
        plan.elapsed_seconds,
        plan.cpu_seconds,
        plan.peak_rss_bytes,
    )
    assert plan_reasons_and_migrations(plan.payload) == (
        test_case.expected_query_changed,
        test_case.expected_migrations,
    )
    assert plan.elapsed_seconds < test_case.expected_max_wall_seconds
    assert plan.peak_rss_bytes < test_case.expected_max_rss_bytes


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
