"""Rules benchmark project construction and scenario workflow."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from scripts.rules_benchmark.constants import NON_CACHEABLE_REJECTION, SQL_SUFFIX
from scripts.rules_benchmark.exceptions import RulesBenchmarkError
from scripts.rules_benchmark.models import BenchmarkResult
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    write_layered_production_compile_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.rules.helpers import write_custom_rules

_COMPILE_TIMEOUT_SECONDS: int = 300


def run_benchmark(*, model_count: int, iterations: int, output: Path | None) -> int:
    """Generate a representative project, execute scenarios, and render measurements."""
    with tempfile.TemporaryDirectory(prefix="sqlbuild-rules-benchmark-") as temporary:
        project_dir: Path = Path(temporary) / "project"
        _write_project(project_dir=project_dir, model_count=model_count)
        results: tuple[BenchmarkResult, ...] = _run_scenarios(
            project_dir=project_dir, model_count=model_count, iterations=iterations
        )
        workload: dict[str, int] = _workload_counts(project_dir=project_dir)
    payload: dict[str, object] = {
        "hardware": _hardware_payload(),
        "iterations": iterations,
        "model_count": model_count,
        "custom_rule_count": 20,
        "multi_edit_model_count": _multi_edit_model_count(model_count),
        "versions": _version_payload(),
        "workload": workload,
        "scenarios": [_result_payload(result=result) for result in results],
    }
    return _write_benchmark_payload(payload=payload, output=output)


def run_rule_count_benchmark(
    *, model_count: int, iterations: int, rule_counts: tuple[int, ...], output: Path | None
) -> int:
    """Measure custom-rule count scaling against one stable generated project."""

    with tempfile.TemporaryDirectory(prefix="sqlbuild-rule-count-benchmark-") as temporary:
        project_dir: Path = Path(temporary) / "project"
        _write_project(project_dir=project_dir, model_count=model_count)
        _ = _invoke(project_dir)
        profiles: list[dict[str, object]] = []
        _write_rule_count_checkpoint(
            output=output,
            model_count=model_count,
            iterations=iterations,
            rule_counts=rule_counts,
            profiles=profiles,
            complete=False,
        )
        for rule_count in rule_counts:
            write_custom_rules(project_dir=project_dir, rule_count=rule_count)
            cold: BenchmarkResult = _measure(
                scenario="cold",
                project_dir=project_dir,
                iterations=iterations,
                mutate=lambda iteration: _clear_cache(project_dir),
            )
            _ = _invoke(project_dir)
            warm: BenchmarkResult = _measure(
                scenario="unchanged_warm",
                project_dir=project_dir,
                iterations=iterations,
                mutate=lambda iteration: None,
            )
            multi_edit: BenchmarkResult = _measure(
                scenario="multi_model_edit",
                project_dir=project_dir,
                iterations=iterations,
                mutate=lambda iteration: _append_model_markers(
                    project_dir=project_dir,
                    model_count=model_count,
                    edit_count=_multi_edit_model_count(model_count),
                    iteration=iteration,
                ),
            )
            rule_edit: BenchmarkResult = _measure(
                scenario="custom_rule_source_edit",
                project_dir=project_dir,
                iterations=iterations,
                mutate=lambda iteration: _mutate_custom_rule(
                    path=project_dir / "rules" / "benchmark_rules.py"
                ),
            )
            profiles.append(
                {
                    "custom_rule_count": rule_count,
                    "cache_bytes": _rules_cache_bytes(project_dir),
                    "scenarios": [
                        _result_payload(result=result)
                        for result in (cold, warm, multi_edit, rule_edit)
                    ],
                }
            )
            _write_rule_count_checkpoint(
                output=output,
                model_count=model_count,
                iterations=iterations,
                rule_counts=rule_counts,
                profiles=profiles,
                complete=False,
            )
        workload: dict[str, int] = _workload_counts(project_dir=project_dir)
    return _write_benchmark_payload(
        payload={
            "benchmark": "custom_rule_count_scaling",
            "complete": True,
            "hardware": _hardware_payload(),
            "iterations": iterations,
            "model_count": model_count,
            "multi_edit_model_count": _multi_edit_model_count(model_count),
            "rule_counts": rule_counts,
            "versions": _version_payload(),
            "workload": workload,
            "profiles": profiles,
        },
        output=output,
    )


def _write_project(*, project_dir: Path, model_count: int) -> None:
    write_layered_production_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        source_count=_scaled_count(model_count=model_count, representative_count=232),
        seed_count=_scaled_count(model_count=model_count, representative_count=46),
        function_count=_scaled_count(model_count=model_count, representative_count=23),
        macro_count=_scaled_count(model_count=model_count, representative_count=12),
        test_count=_scaled_count(model_count=model_count, representative_count=130),
        audit_count=_scaled_count(model_count=model_count, representative_count=700),
    )
    write_custom_rules(project_dir=project_dir)
    config: Path = project_dir / "sqlbuild_project.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + (
            '\n[rules]\nselect = ["SQBRSQL001", "XSQBR"]\n'
            "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n"
            "[rules.cache]\nenabled = true\n"
        ),
        encoding="utf-8",
    )


def _run_scenarios(
    *, project_dir: Path, model_count: int, iterations: int
) -> tuple[BenchmarkResult, ...]:
    results: list[BenchmarkResult] = [
        _measure(
            scenario="cold",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _clear_cache(project_dir),
        )
    ]
    _ = _invoke(project_dir)
    results.append(
        _measure(
            scenario="tracked_rule_input_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _append_marker(
                path=project_dir / "rules" / "benchmark_input.yaml",
                scenario="rule-input",
                iteration=iteration,
            ),
        )
    )
    results.append(
        _measure(
            scenario="unchanged_warm",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: None,
        )
    )
    finding_path: Path = _generated_model_path(project_dir=project_dir, index=model_count - 1)
    _inject_sql_finding(path=finding_path)
    results.append(
        _measure(
            scenario="failing_rule",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: None,
            allow_failure=True,
        )
    )
    _remove_sql_finding(path=finding_path)
    _ = _invoke(project_dir)
    results.append(
        _measure(
            scenario="leaf_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _append_marker(
                path=_generated_model_path(project_dir=project_dir, index=model_count - 1),
                scenario="leaf",
                iteration=iteration,
            ),
        )
    )
    results.append(
        _measure(
            scenario="multi_model_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _append_model_markers(
                project_dir=project_dir,
                model_count=model_count,
                edit_count=_multi_edit_model_count(model_count),
                iteration=iteration,
            ),
        )
    )
    results.append(
        _measure(
            scenario="shared_ancestor_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _append_marker(
                path=_generated_model_path(project_dir=project_dir, index=0),
                scenario="ancestor",
                iteration=iteration,
            ),
        )
    )
    results.append(
        _measure(
            scenario="custom_rule_source_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _mutate_custom_rule(
                path=project_dir / "rules" / "benchmark_rules.py"
            ),
        )
    )
    config: Path = project_dir / "sqlbuild_project.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("enabled = true", "enabled = false"),
        encoding="utf-8",
    )
    results.append(
        _measure(
            scenario="cache_disabled",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: None,
        )
    )
    config.write_text(
        config.read_text(encoding="utf-8").replace("enabled = false", "enabled = true"),
        encoding="utf-8",
    )
    results.append(
        _measure_rejection(
            project_dir=project_dir,
            iterations=iterations,
        )
    )
    return tuple(results)


def _measure(
    *,
    scenario: str,
    project_dir: Path,
    iterations: int,
    mutate: Callable[[int], None],
    allow_failure: bool = False,
) -> BenchmarkResult:
    elapsed: list[float] = []
    core_ms: list[int] = []
    built_in_rules_ms: list[int] = []
    custom_rules_ms: list[int] = []
    payload: dict[str, object] = {}
    for iteration in range(iterations):
        mutate(iteration)
        started: float = time.perf_counter()
        payload = _invoke(project_dir, allow_failure=allow_failure)
        elapsed.append(time.perf_counter() - started)
        timings: object = payload.get("compile_timings")
        if not isinstance(timings, dict):
            raise RulesBenchmarkError("Rules benchmark returned no compile timings")
        timing_values: dict[str, object] = {str(key): value for key, value in timings.items()}
        core_ms.append(
            sum(
                _integer(payload=timing_values, key=key)
                for key in ("discover_ms", "graph_ms", "lineage_ms", "contracts_ms")
            )
        )
        built_in_rules_ms.append(_integer(payload=timing_values, key="built_in_rules_ms"))
        custom_rules_ms.append(_integer(payload=timing_values, key="custom_rules_ms"))
    summary: object = payload.get("summary")
    timings = payload.get("compile_timings")
    if not isinstance(summary, dict) or not isinstance(timings, dict):
        raise RulesBenchmarkError("Rules benchmark returned incomplete compile output")
    summary_values: dict[str, object] = {str(key): value for key, value in summary.items()}
    timing_values = {str(key): value for key, value in timings.items()}
    return BenchmarkResult(
        scenario=scenario,
        seconds=tuple(elapsed),
        evaluated_models=_integer(payload=summary_values, key="selected_models"),
        cache_hits=_integer(payload=timing_values, key="rule_cache_hits"),
        cache_misses=_integer(payload=timing_values, key="rule_cache_misses"),
        core_ms=tuple(core_ms),
        built_in_rules_ms=tuple(built_in_rules_ms),
        custom_rules_ms=tuple(custom_rules_ms),
    )


def _invoke(project_dir: Path, *, allow_failure: bool = False) -> dict[str, object]:
    result: subprocess.CompletedProcess[str] = _run(project_dir)
    accepted_codes: tuple[int, ...] = (0, 1) if allow_failure else (0,)
    if result.returncode not in accepted_codes or not result.stdout:
        raise RulesBenchmarkError(result.stderr or "Rules benchmark produced no output")
    return json.loads(result.stdout)


def _run(project_dir: Path) -> subprocess.CompletedProcess[str]:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "compile",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=_COMPILE_TIMEOUT_SECONDS,
    )
    return result


def _measure_rejection(*, project_dir: Path, iterations: int) -> BenchmarkResult:
    rule_file: Path = project_dir / "rules" / "benchmark_rules.py"
    with rule_file.open("a", encoding="utf-8") as handle:
        handle.write("\ndef non_cacheable_probe():\n    return open('untracked.txt')\n")
    elapsed: list[float] = []
    for _ in range(iterations):
        started: float = time.perf_counter()
        result: subprocess.CompletedProcess[str] = _run(project_dir)
        elapsed.append(time.perf_counter() - started)
        detail: str = f"{result.stderr}\n{result.stdout}".strip()
        if result.returncode == 0 or NON_CACHEABLE_REJECTION not in detail:
            raise RulesBenchmarkError(f"non-cacheable custom rule was not rejected: {detail}")
    return BenchmarkResult(
        scenario="non_cacheable_rejection",
        seconds=tuple(elapsed),
        evaluated_models=0,
        cache_hits=0,
        cache_misses=0,
        rejected=True,
    )


def _integer(*, payload: dict[str, object], key: str) -> int:
    value: object = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RulesBenchmarkError(f"Rules benchmark returned invalid {key}")
    return value


def _clear_cache(project_dir: Path) -> None:
    cache: Path = project_dir / "target" / "rules-cache"
    if cache.exists():
        shutil.rmtree(cache)


def _append_marker(*, path: Path, scenario: str, iteration: int) -> None:
    prefix: str = "--" if path.suffix == SQL_SUFFIX else "#"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n{prefix} benchmark {scenario} {iteration}\n")


def _append_model_markers(
    *, project_dir: Path, model_count: int, edit_count: int, iteration: int
) -> None:
    for index in range(model_count - edit_count, model_count):
        _append_marker(
            path=_generated_model_path(project_dir=project_dir, index=index),
            scenario="multi-model",
            iteration=iteration,
        )


def _multi_edit_model_count(model_count: int) -> int:
    return max(1, model_count // 100)


def _mutate_custom_rule(*, path: Path) -> None:
    source: str = path.read_text(encoding="utf-8")
    plain: str = (
        "def check_003(*, model: Model, ctx: RuleContext) -> list[Finding]:\n    select_count = 1"
    )
    changed: str = (
        "def check_003(*, model: Model, ctx: RuleContext) -> list[Finding]:\n"
        "    select_count = (1 + 0)"
    )
    project_plain: str = 'content = ctx.project.tree.read_text("rules/benchmark_input.yaml")'
    project_changed: str = 'content = (ctx.project.tree.read_text("rules/benchmark_input.yaml"))'
    if plain in source:
        source = source.replace(plain, changed, 1)
    elif changed in source:
        source = source.replace(changed, plain, 1)
    elif project_plain in source:
        source = source.replace(project_plain, project_changed, 1)
    elif project_changed in source:
        source = source.replace(project_changed, project_plain, 1)
    else:
        raise RulesBenchmarkError("could not locate custom rule implementation marker")
    path.write_text(source, encoding="utf-8")


def _inject_sql_finding(*, path: Path) -> None:
    source: str = path.read_text(encoding="utf-8")
    marker: str = "SELECT\n"
    if marker not in source:
        raise RulesBenchmarkError("could not locate SQL finding marker")
    path.write_text(
        source.replace(marker, f"{marker}  NULL = NULL AS invalid_null_comparison,\n", 1),
        encoding="utf-8",
    )


def _remove_sql_finding(*, path: Path) -> None:
    source: str = path.read_text(encoding="utf-8")
    path.write_text(
        source.replace("  NULL = NULL AS invalid_null_comparison,\n", "", 1),
        encoding="utf-8",
    )


def _result_payload(*, result: BenchmarkResult) -> dict[str, object]:
    ordered: list[float] = sorted(result.seconds)
    p95_index: int = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return {
        "scenario": result.scenario,
        "median_seconds": statistics.median(result.seconds),
        "p95_seconds": ordered[p95_index],
        "samples_seconds": result.seconds,
        "evaluated_models": result.evaluated_models,
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
        "core_ms": _distribution(result.core_ms),
        "built_in_rules_ms": _distribution(result.built_in_rules_ms),
        "custom_rules_ms": _distribution(result.custom_rules_ms),
        "rejected": result.rejected,
    }


def _distribution(values: tuple[int, ...]) -> dict[str, object] | None:
    if not values:
        return None
    ordered: list[int] = sorted(values)
    p95_index: int = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return {
        "median_ms": statistics.median(values),
        "p95_ms": ordered[p95_index],
        "samples_ms": values,
    }


def _cpu_model() -> str:
    cpuinfo: Path = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.partition(":")[2].strip()
    return platform.processor() or "unknown"


def _memory_bytes() -> int | None:
    meminfo: Path = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    return None


def _hardware_payload() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu": _cpu_model(),
        "logical_cpus": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
    }


def _version_payload() -> dict[str, str]:
    return {
        "sqlbuild": importlib.metadata.version("sqlbuild"),
        "polyglot_sql": importlib.metadata.version("polyglot-sql"),
    }


def _write_benchmark_payload(*, payload: dict[str, object], output: Path | None) -> int:
    rendered: str = json.dumps(payload, indent=2, sort_keys=True)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _write_rule_count_checkpoint(
    *,
    output: Path | None,
    model_count: int,
    iterations: int,
    rule_counts: tuple[int, ...],
    profiles: list[dict[str, object]],
    complete: bool,
) -> None:
    if output is None:
        return
    payload: dict[str, object] = {
        "benchmark": "custom_rule_count_scaling",
        "complete": complete,
        "hardware": _hardware_payload(),
        "iterations": iterations,
        "model_count": model_count,
        "multi_edit_model_count": _multi_edit_model_count(model_count),
        "rule_counts": rule_counts,
        "versions": _version_payload(),
        "profiles": profiles,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _rules_cache_bytes(project_dir: Path) -> int:
    cache_dir: Path = project_dir / "target" / "rules-cache"
    return sum(path.stat().st_size for path in cache_dir.rglob("*") if path.is_file())


def _workload_counts(*, project_dir: Path) -> dict[str, int]:
    model_paths: tuple[Path, ...] = tuple((project_dir / "models").rglob("*.sql"))
    test_paths: tuple[Path, ...] = tuple((project_dir / "tests").rglob("*.sql"))
    rule_paths: tuple[Path, ...] = tuple((project_dir / "rules").rglob("*.py"))
    sources_text: str = "\n".join(
        path.read_text(encoding="utf-8") for path in (project_dir / "sources").rglob("*.yml")
    )
    return {
        "models": len(model_paths),
        "sources": sources_text.count("  - name: source_"),
        "seeds": sum(1 for _ in (project_dir / "seeds").rglob("*.csv")),
        "functions": sum(1 for _ in (project_dir / "functions").rglob("*.sql")),
        "macros": sum(1 for _ in (project_dir / "models" / "macros").rglob("*.py")),
        "tests": sum(path.read_text(encoding="utf-8").count("TEST (") for path in test_paths),
        "audits": sum(path.read_text(encoding="utf-8").count("audits [") for path in model_paths),
        "hooks": sum(1 for _ in (project_dir / "hooks").rglob("*.sql")),
        "custom_rules": sum(
            path.read_text(encoding="utf-8").count("@rule(") for path in rule_paths
        ),
    }


def _scaled_count(*, model_count: int, representative_count: int) -> int:
    return max(1, round(model_count * representative_count / 976))


def _generated_model_path(*, project_dir: Path, index: int) -> Path:
    matches: tuple[Path, ...] = tuple((project_dir / "models").rglob(f"model_{index:05d}.sql"))
    if len(matches) != 1:
        raise RulesBenchmarkError(f"expected one generated model path for index {index}")
    return matches[0]
