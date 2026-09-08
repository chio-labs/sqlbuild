"""Project Policy benchmark project construction and scenario workflow."""

from __future__ import annotations

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

from scripts.project_policy_benchmark.constants import NON_CACHEABLE_REJECTION, SQL_SUFFIX
from scripts.project_policy_benchmark.exceptions import PolicyBenchmarkError
from scripts.project_policy_benchmark.models import BenchmarkResult
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import write_advanced_compile_project
from tests.e2e.src.sqlbuild.cli.commands.main.policy.helpers import write_custom_policy_rules


def run_benchmark(*, model_count: int, iterations: int, output: Path | None) -> int:
    """Generate a representative project, execute scenarios, and render measurements."""
    with tempfile.TemporaryDirectory(prefix="sqlbuild-policy-benchmark-") as temporary:
        project_dir: Path = Path(temporary)
        _write_project(project_dir=project_dir, model_count=model_count)
        results: tuple[BenchmarkResult, ...] = _run_scenarios(
            project_dir=project_dir, model_count=model_count, iterations=iterations
        )
    payload: dict[str, object] = {
        "hardware": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "cpu": _cpu_model(),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": _memory_bytes(),
        },
        "iterations": iterations,
        "model_count": model_count,
        "custom_policy_count": 20,
        "scenarios": [_result_payload(result=result) for result in results],
    }
    rendered: str = json.dumps(payload, indent=2, sort_keys=True)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def _write_project(*, project_dir: Path, model_count: int) -> None:
    write_advanced_compile_project(project_dir=project_dir, model_count=model_count)
    write_custom_policy_rules(project_dir=project_dir)
    config: Path = project_dir / "sqlbuild_project.toml"
    config.write_text(
        config.read_text(encoding="utf-8")
        + (
            '\n[policy]\nselect = ["SQBP", "XSQBP"]\n'
            'rule_paths = ["policy/benchmark_rules.py"]\n\n'
            "[policy.cache]\nenabled = true\nrequire_cacheable = true\n"
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
            scenario="tracked_policy_input_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _append_marker(
                path=project_dir / "policy" / "benchmark_input.yaml",
                scenario="policy-input",
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
    results.append(
        _measure(
            scenario="leaf_edit",
            project_dir=project_dir,
            iterations=iterations,
            mutate=lambda iteration: _append_marker(
                path=project_dir / "models" / f"model_{model_count - 1:05d}.sql",
                scenario="leaf",
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
                path=project_dir / "models" / "model_00000.sql",
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
            mutate=lambda iteration: _append_marker(
                path=project_dir / "policy" / "benchmark_rules.py",
                scenario="rule",
                iteration=iteration,
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
    *, scenario: str, project_dir: Path, iterations: int, mutate: Callable[[int], None]
) -> BenchmarkResult:
    elapsed: list[float] = []
    payload: dict[str, object] = {}
    for iteration in range(iterations):
        mutate(iteration)
        started: float = time.perf_counter()
        payload = _invoke(project_dir)
        elapsed.append(time.perf_counter() - started)
    return BenchmarkResult(
        scenario=scenario,
        seconds=tuple(elapsed),
        evaluated_models=_integer(payload=payload, key="evaluated_models"),
        cache_hits=_integer(payload=payload, key="cache_hits"),
        cache_misses=_integer(payload=payload, key="cache_misses"),
    )


def _invoke(project_dir: Path) -> dict[str, object]:
    result: subprocess.CompletedProcess[str] = _run(project_dir)
    if result.returncode not in (0, 1) or not result.stdout:
        raise PolicyBenchmarkError(result.stderr or "Project Policy benchmark produced no output")
    return json.loads(result.stdout)


def _run(project_dir: Path) -> subprocess.CompletedProcess[str]:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "policy",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result


def _measure_rejection(*, project_dir: Path, iterations: int) -> BenchmarkResult:
    rule_file: Path = project_dir / "policy" / "benchmark_rules.py"
    with rule_file.open("a", encoding="utf-8") as handle:
        handle.write("\ndef non_cacheable_probe():\n    return open('untracked.txt')\n")
    elapsed: list[float] = []
    for _ in range(iterations):
        started: float = time.perf_counter()
        result: subprocess.CompletedProcess[str] = _run(project_dir)
        elapsed.append(time.perf_counter() - started)
        if result.returncode == 0 or NON_CACHEABLE_REJECTION not in result.stderr:
            detail: str = result.stderr.strip() or result.stdout.strip()
            raise PolicyBenchmarkError(f"non-cacheable custom policy was not rejected: {detail}")
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
        raise PolicyBenchmarkError(f"Project Policy benchmark returned invalid {key}")
    return value


def _clear_cache(project_dir: Path) -> None:
    cache: Path = project_dir / "target" / "policy-cache"
    if cache.exists():
        shutil.rmtree(cache)


def _append_marker(*, path: Path, scenario: str, iteration: int) -> None:
    prefix: str = "--" if path.suffix == SQL_SUFFIX else "#"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n{prefix} benchmark {scenario} {iteration}\n")


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
        "rejected": result.rejected,
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
