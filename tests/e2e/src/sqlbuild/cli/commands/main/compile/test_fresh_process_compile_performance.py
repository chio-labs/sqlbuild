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
            expected_max_wall_seconds=15.0,
            expected_max_rss_bytes=2 * _GIB,
            expected_semantic_fingerprint=(
                "02af81fb7723d30ec5082ed06fb039e45acba3d60b2d8a30fcbccb5a990bb9fc"
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
            expected_max_wall_seconds=20.0,
            expected_max_rss_bytes=2 * _GIB,
            expected_semantic_fingerprint=(
                "0c9258635fe4f9d31ec2dd1c99dbc63f5c8551ca7fea494003c5ab1c3a2ad57c"
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
            expected_max_wall_seconds=38.0,
            expected_max_rss_bytes=2 * _GIB,
            expected_semantic_fingerprint=(
                "6887ddd2547137efd8fe67d13fb07142f6287c0911d152d69eca0d495310e02b"
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
        "fresh-process semantic compile models=%d wall=%.3fs peak_rss_bytes=%d fingerprint=%s",
        test_case.model_count,
        result.elapsed_seconds,
        result.peak_rss_bytes,
        result.semantic_fingerprint,
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
