"""Performance guards for real Scope Explorer project loading and cache reuse."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scope._test_types import (
    LargeScopePerformanceCase,
    ScopePerformanceCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scope.helpers import (
    measure_cold_scope_commands,
    measure_warm_scope_commands,
    median_seconds,
    scope_cache_path,
    write_scope_performance_project,
)

_LARGE_BENCHMARK_ENV: str = "SQLBUILD_RUN_LARGE_SCOPE_BENCHMARK"
_LOGGER: logging.Logger = logging.getLogger(__name__)


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        ScopePerformanceCase(
            description="doubling models and inherited macros keeps cold scope scaling bounded",
            small_model_count=1_000,
            small_domain_count=10,
            large_model_count=2_000,
            large_domain_count=20,
            sample_count=3,
            expected_max_small_seconds=8.0,
            expected_max_large_seconds=18.0,
            expected_max_warm_seconds=4.0,
            expected_max_scaling_ratio=3.0,
            expected_max_cache_bytes=16 * 1024 * 1024,
            command_timeout_seconds=30.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_domain_shaped_projects_when_doubling_size_then_scope_scaling_stays_bounded(
    tmp_path: Path,
    test_case: ScopePerformanceCase,
    record_property: Callable[[str, object], None],
) -> None:
    small_project: Path = tmp_path / "small"
    large_project: Path = tmp_path / "large"
    write_scope_performance_project(
        project_dir=small_project,
        model_count=test_case.small_model_count,
        domain_count=test_case.small_domain_count,
    )
    write_scope_performance_project(
        project_dir=large_project,
        model_count=test_case.large_model_count,
        domain_count=test_case.large_domain_count,
    )

    small_cold: float = median_seconds(
        measure_cold_scope_commands(
            project_dir=small_project,
            target="model:model_00000",
            sample_count=test_case.sample_count,
            timeout_seconds=test_case.command_timeout_seconds,
        )
    )
    large_cold: float = median_seconds(
        measure_cold_scope_commands(
            project_dir=large_project,
            target="model:model_00000",
            sample_count=test_case.sample_count,
            timeout_seconds=test_case.command_timeout_seconds,
        )
    )
    large_warm: float = median_seconds(
        measure_warm_scope_commands(
            project_dir=large_project,
            target="model:model_00000",
            sample_count=test_case.sample_count,
            timeout_seconds=test_case.command_timeout_seconds,
        )
    )
    cache_bytes: int = scope_cache_path(project_dir=large_project).stat().st_size
    scaling_ratio: float = large_cold / small_cold
    for name, value in (
        ("small_cold_seconds", small_cold),
        ("large_cold_seconds", large_cold),
        ("large_warm_seconds", large_warm),
        ("cold_scaling_ratio", scaling_ratio),
        ("cache_bytes", cache_bytes),
    ):
        record_property(name, value)
    _LOGGER.info(
        f"scope scaling small={small_cold:.3f}s large={large_cold:.3f}s "
        f"warm={large_warm:.3f}s ratio={scaling_ratio:.3f} cache={cache_bytes}B"
    )

    assert small_cold < test_case.expected_max_small_seconds
    assert large_cold < test_case.expected_max_large_seconds
    assert large_warm < test_case.expected_max_warm_seconds
    assert scaling_ratio < test_case.expected_max_scaling_ratio
    assert cache_bytes < test_case.expected_max_cache_bytes


@pytest.mark.performance
@pytest.mark.skipif(
    os.environ.get(_LARGE_BENCHMARK_ENV) != "1",
    reason=f"Set {_LARGE_BENCHMARK_ENV}=1 for the scheduled large benchmark",
)
@pytest.mark.parametrize(
    "test_case",
    [
        LargeScopePerformanceCase(
            description="ten thousand models and one thousand macros remain cacheable",
            model_count=10_000,
            domain_count=100,
            warm_sample_count=3,
            expected_max_cold_seconds=90.0,
            expected_max_warm_seconds=10.0,
            expected_max_cache_bytes=16 * 1024 * 1024,
            command_timeout_seconds=120.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_large_domain_project_when_inspecting_scope_then_records_cold_and_warm_cost(
    tmp_path: Path,
    test_case: LargeScopePerformanceCase,
    record_property: Callable[[str, object], None],
) -> None:
    project_dir: Path = tmp_path / "large_scope"
    write_scope_performance_project(
        project_dir=project_dir,
        model_count=test_case.model_count,
        domain_count=test_case.domain_count,
    )

    cold_seconds: float = median_seconds(
        measure_cold_scope_commands(
            project_dir=project_dir,
            target="model:model_00000",
            sample_count=1,
            timeout_seconds=test_case.command_timeout_seconds,
        )
    )
    warm_seconds: float = median_seconds(
        measure_warm_scope_commands(
            project_dir=project_dir,
            target="model:model_00000",
            sample_count=test_case.warm_sample_count,
            timeout_seconds=test_case.command_timeout_seconds,
        )
    )
    cache_bytes: int = scope_cache_path(project_dir=project_dir).stat().st_size
    for name, value in (
        ("cold_seconds", cold_seconds),
        ("warm_seconds", warm_seconds),
        ("cache_bytes", cache_bytes),
    ):
        record_property(name, value)
    _LOGGER.info(
        f"large scope models={test_case.model_count} macros={test_case.domain_count * 10} "
        f"cold={cold_seconds:.3f}s warm={warm_seconds:.3f}s cache={cache_bytes}B"
    )

    assert cold_seconds < test_case.expected_max_cold_seconds
    assert warm_seconds < test_case.expected_max_warm_seconds
    assert cache_bytes < test_case.expected_max_cache_bytes


if __name__ == "__main__":
    pytest.main([__file__, "-vv", "-s", "--log-cli-level=INFO"])
