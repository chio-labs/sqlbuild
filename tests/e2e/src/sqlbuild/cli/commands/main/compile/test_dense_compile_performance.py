"""Fresh-process guards for dense query graphs and the complete built-in ruleset."""

from itertools import filterfalse
from operator import attrgetter
from pathlib import Path
from typing import cast

import pytest

from scripts.cold_compile_performance._helpers.dense_project import (
    write_dense_compile_project,
)
from scripts.cold_compile_performance.main.assert_required_cgroup_memory_limit import (
    assert_required_cgroup_memory_limit,
)
from sqlbuild.rule_engine._helpers.engine.catalogue import build_catalogue, select_rules
from sqlbuild.rule_engine.main.load_config import load_rules_config
from sqlbuild.rule_engine.models import Rule, RulesConfig
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    DenseCompileGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    FreshProcessCompileBenchmarkResult,
    _run_fresh_process_compile_benchmark,
    measure_model_sql_bytes,
)

_GIB: int = 1024 * 1024 * 1024


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    (
        DenseCompileGuardTestCase(
            "dense_models_1000_all_rules",
            1000,
            14.0,
            3 * _GIB // 2,
            "99f2f5c698cca3c7f0d5a2defbd31935d98813843c899286a23a8e7d4441a736",
        ),
        DenseCompileGuardTestCase(
            "dense_models_3000_all_rules",
            3000,
            34.0,
            11 * _GIB // 4,
            "1243f3de95857de4e7d1d8563ae6766aa9d2a192cf7525cec8ef5562b12704dc",
        ),
        DenseCompileGuardTestCase(
            "dense_models_5000_all_rules",
            5000,
            55.0,
            13 * _GIB // 4,
            "956135597584ec369d37c23ab91b01bc6bf2df9ba78dce602311e152d451fa90",
        ),
        DenseCompileGuardTestCase(
            "dense_models_10000_all_rules",
            10000,
            145.0,
            4 * _GIB,
            "92bf43fc45084c67de0eab3d4f32160e8303f99e1b951f6a7a1da5660f0eb66b",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dense_project_when_compiling_cold_then_preserves_rules_semantics_and_budgets(
    test_case: DenseCompileGuardTestCase,
    tmp_path: Path,
) -> None:
    assert_required_cgroup_memory_limit()
    project_dir: Path = tmp_path / "dense_orders"
    write_dense_compile_project(project_dir=project_dir, model_count=test_case.model_count)
    config: RulesConfig = load_rules_config(project_dir=project_dir)
    catalogue: tuple[Rule, ...] = build_catalogue(config=config, project_dir=project_dir)
    selected: tuple[Rule, ...] = select_rules(
        catalogue=catalogue, config=config, project_dir=project_dir
    )
    builtin_codes: set[str] = {rule.code for rule in filterfalse(attrgetter("custom"), catalogue)}
    assert len(builtin_codes) >= 75
    assert {rule.code for rule in filterfalse(attrgetter("custom"), selected)} == builtin_codes
    assert sum(rule.custom for rule in selected) == 1
    assert not config.rule_exceptions
    assert not config.rule_ignores
    assert not config.ignore
    assert not config.thresholds
    assert measure_model_sql_bytes(project_dir) >= 7000 * test_case.model_count
    result: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"dense-{test_case.model_count}",
        expected_max_wall_seconds=test_case.expected_max_wall_seconds,
        compile_args=("--no-cache",),
    )
    print(
        f"dense compile models={test_case.model_count} builtin_rules={len(builtin_codes)} "
        f"fingerprint={result.semantic_fingerprint}",
        flush=True,
    )
    assert result.payload["diagnostics"] == []
    assert result.payload["has_errors"] is False
    assert result.payload["summary"] == {
        "models": test_case.model_count,
        "selected_models": test_case.model_count,
        "sources": test_case.model_count * 24 // 100,
        "seeds": test_case.model_count // 20,
        "selected_seeds": test_case.model_count // 20,
        "functions": test_case.model_count // 40,
        "selected_functions": test_case.model_count // 40,
        "audits": test_case.model_count * 17 // 10,
        "tests": test_case.model_count,
        "hooks": 0,
        "execution_layers": 48,
        "errors": 0,
        "warnings": 0,
    }
    timings: dict[str, int] = cast(dict[str, int], result.payload["compile_timings"])
    assert timings["analysis_cache_bypasses"] == test_case.model_count
    assert timings["analysis_entry_cache_hits"] == timings["analysis_batch_cache_hits"] == 0
    assert timings["rule_cache_hits"] == 0
    assert timings["rule_cache_misses"] == 2 * test_case.model_count + 1
    assert timings["built_in_rules_ms"] > 0
    assert timings["custom_rules_ms"] > 0
    assert result.semantic_fingerprint == test_case.expected_fingerprint
    assert result.elapsed_seconds < test_case.expected_max_wall_seconds
    assert result.peak_rss_bytes < test_case.expected_max_rss_bytes


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
