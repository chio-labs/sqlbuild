"""Fresh-process performance guards for representative semantic projects."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scripts.cold_compile_performance.main.assert_required_cgroup_memory_limit import (
    assert_required_cgroup_memory_limit,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    FreshProcessCompilePerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    FreshProcessCompileBenchmarkResult,
    run_fresh_process_semantic_compile_benchmark,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)
_GIB: int = 1024 * 1024 * 1024


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        FreshProcessCompilePerformanceGuardTestCase(
            description="models_3000_fresh_process_semantic_compile_stays_within_budget",
            model_count=3_000,
            source_count=713,
            seed_count=141,
            function_count=71,
            macro_count=37,
            test_count=2_945,
            audit_count=5_056,
            expected_max_wall_seconds=11.0,
            expected_max_rss_bytes=int(1.5 * _GIB),
            expected_semantic_fingerprint=(
                "c8b7b6d5d2033560abd141b612f383a7dd1ce136c6a72e9d685e08dcbc1de2db"
            ),
        ),
        FreshProcessCompilePerformanceGuardTestCase(
            description="models_5000_fresh_process_semantic_compile_stays_within_budget",
            model_count=5_000,
            source_count=1_189,
            seed_count=236,
            function_count=118,
            macro_count=61,
            test_count=4_908,
            audit_count=8_427,
            expected_max_wall_seconds=15.5,
            expected_max_rss_bytes=int(1.75 * _GIB),
            expected_semantic_fingerprint=(
                "416e0a037d1d67a242f1ad39da463ca26cd24146b81d4991ce035015d6d18106"
            ),
        ),
        FreshProcessCompilePerformanceGuardTestCase(
            description="models_10000_fresh_process_semantic_compile_stays_within_budget",
            model_count=10_000,
            source_count=2_377,
            seed_count=471,
            function_count=236,
            macro_count=123,
            test_count=9_816,
            audit_count=16_855,
            expected_max_wall_seconds=29.5,
            expected_max_rss_bytes=2 * _GIB,
            expected_semantic_fingerprint=(
                "f421d6b6269c8836963bcea0724a619ec10939f33274f69bc3fa5625f81ef49b"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scaled_semantic_project_when_compiling_fresh_then_preserves_resource_budgets(
    tmp_path: Path,
    test_case: FreshProcessCompilePerformanceGuardTestCase,
) -> None:
    assert_required_cgroup_memory_limit()
    result: FreshProcessCompileBenchmarkResult = run_fresh_process_semantic_compile_benchmark(
        project_dir=tmp_path / f"semantic_{test_case.model_count}",
        model_count=test_case.model_count,
        source_count=test_case.source_count,
        seed_count=test_case.seed_count,
        function_count=test_case.function_count,
        macro_count=test_case.macro_count,
        test_count=test_case.test_count,
        audit_count=test_case.audit_count,
        expected_max_wall_seconds=test_case.expected_max_wall_seconds,
    )
    _LOGGER.info(
        "fresh-process semantic compile models=%d wall=%.3fs peak_rss_bytes=%d "
        "fingerprint=%s timings=%s",
        test_case.model_count,
        result.elapsed_seconds,
        result.peak_rss_bytes,
        result.semantic_fingerprint,
        result.payload["compile_timings"],
    )

    assert result.payload["has_errors"] is False
    assert result.payload["diagnostics"] == []
    assert result.payload["summary"] == {
        "models": test_case.model_count,
        "selected_models": test_case.model_count,
        "sources": test_case.source_count,
        "seeds": test_case.seed_count,
        "selected_seeds": test_case.seed_count,
        "functions": test_case.function_count,
        "selected_functions": test_case.function_count,
        "audits": test_case.audit_count,
        "tests": test_case.test_count,
        "hooks": 2,
        "execution_layers": 54,
        "errors": 0,
        "warnings": 0,
    }
    assert result.semantic_fingerprint == test_case.expected_semantic_fingerprint
    assert result.elapsed_seconds < test_case.expected_max_wall_seconds
    assert result.peak_rss_bytes < test_case.expected_max_rss_bytes
