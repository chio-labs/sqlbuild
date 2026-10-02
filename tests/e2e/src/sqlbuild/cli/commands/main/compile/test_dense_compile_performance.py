"""Fresh-process guards for dense query graphs and the complete built-in ruleset."""

from itertools import filterfalse
from operator import attrgetter
from pathlib import Path
from typing import cast

import pytest

from scripts.cold_compile_performance._helpers.dense_project import (
    dense_model_name,
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
    DenseWarmEditCompileGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    FreshProcessCompileBenchmarkResult,
    _run_fresh_process_compile_benchmark,
    fresh_process_compile_cache_metrics,
    measure_model_sql_bytes,
    run_dense_warm_edit_benchmark,
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
            "cfb7bc162018ddc64f9d03ddd2c316e34a333d4129906d8e0b3310399604b980",
        ),
        DenseCompileGuardTestCase(
            "dense_models_3000_all_rules",
            3000,
            45.0,
            11 * _GIB // 4,
            "c35ea7ec71e6e81059146bc1cd72f10e6493248dc6274aba7737d616d434585b",
        ),
        DenseCompileGuardTestCase(
            "dense_models_5000_all_rules",
            5000,
            75.0,
            13 * _GIB // 4,
            "b07422282a6800de7830b9c4950f76bdc6fd555ebd3f21152b8649f976be74dc",
        ),
        DenseCompileGuardTestCase(
            "dense_models_10000_all_rules",
            10000,
            145.0,
            4 * _GIB,
            "7a4b6cca4a2fd4b7f5961760177f8b18133854014eaf15a980e8283df646a2cf",
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


@pytest.mark.performance
@pytest.mark.cold_compile_performance
@pytest.mark.parametrize(
    "test_case",
    (
        DenseWarmEditCompileGuardTestCase(
            "dense_models_3000_warm_and_one_edit",
            3000,
            1521,
            22.0,
            24.0,
            11 * _GIB // 4,
            "c35ea7ec71e6e81059146bc1cd72f10e6493248dc6274aba7737d616d434585b",
            "255c19bb188491b53d44c2e5d41472137f763806c699f5acb3899c6b47c5360b",
            3,
        ),
        DenseWarmEditCompileGuardTestCase(
            "dense_models_5000_warm_and_one_edit",
            5000,
            2521,
            36.0,
            38.0,
            13 * _GIB // 4,
            "b07422282a6800de7830b9c4950f76bdc6fd555ebd3f21152b8649f976be74dc",
            "c239f53fb5fa787d250f5f7bf404b3731b480b77d2690dd31fb41ba727475fc0",
            3,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dense_project_when_compiling_warm_and_after_one_edit_then_matches_oracle_in_budget(
    test_case: DenseWarmEditCompileGuardTestCase,
    tmp_path: Path,
) -> None:
    assert_required_cgroup_memory_limit()
    project_dir: Path = tmp_path / "dense_orders"
    write_dense_compile_project(project_dir=project_dir, model_count=test_case.model_count)
    index: int = test_case.edited_model_index
    edited_model_path: Path = (
        project_dir
        / "models"
        / f"sales{index // 1000:03d}"
        / "intermediate"
        / "clean"
        / f"batch{index // 5:05d}"
        / f"{dense_model_name(index)}.sql"
    )
    measurements: dict[str, FreshProcessCompileBenchmarkResult] = run_dense_warm_edit_benchmark(
        project_dir=project_dir,
        edited_model_path=edited_model_path,
        expected_warm_max_seconds=test_case.expected_warm_max_seconds,
        expected_edit_max_seconds=test_case.expected_edit_max_seconds,
    )
    for label, result in measurements.items():
        print(
            f"dense {label} models={test_case.model_count} wall={result.elapsed_seconds:.2f}s "
            f"cpu={result.cpu_seconds:.2f}s fingerprint={result.semantic_fingerprint}",
            flush=True,
        )
        assert result.payload["diagnostics"] == []
        assert result.payload["has_errors"] is False
        assert result.peak_rss_bytes < test_case.expected_max_rss_bytes
    cold: FreshProcessCompileBenchmarkResult = measurements["cold"]
    warm: FreshProcessCompileBenchmarkResult = measurements["warm"]
    edit: FreshProcessCompileBenchmarkResult = measurements["edit"]
    assert cold.semantic_fingerprint == test_case.expected_cold_fingerprint
    assert warm.semantic_fingerprint == test_case.expected_cold_fingerprint
    assert edit.semantic_fingerprint == test_case.expected_edit_fingerprint
    assert measurements["oracle"].semantic_fingerprint == test_case.expected_edit_fingerprint
    warm_timings: dict[str, int] = cast(dict[str, int], warm.payload["compile_timings"])
    edit_timings: dict[str, int] = cast(dict[str, int], edit.payload["compile_timings"])
    batch_hits, entry_hits, misses, bypasses = fresh_process_compile_cache_metrics(warm)
    assert (batch_hits + entry_hits, misses, bypasses) == (test_case.model_count, 0, 0)
    assert warm_timings["rule_cache_misses"] == 0
    batch_hits, entry_hits, misses, bypasses = fresh_process_compile_cache_metrics(edit)
    assert 0 < misses < test_case.model_count
    assert batch_hits + entry_hits + misses == test_case.model_count
    assert edit_timings["rule_cache_misses"] == test_case.expected_edit_rule_cache_misses
    oracle_timings: dict[str, int] = cast(
        dict[str, int], measurements["oracle"].payload["compile_timings"]
    )
    assert oracle_timings["rule_cache_hits"] == 0
    assert warm.elapsed_seconds < test_case.expected_warm_max_seconds
    assert edit.elapsed_seconds < test_case.expected_edit_max_seconds


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
