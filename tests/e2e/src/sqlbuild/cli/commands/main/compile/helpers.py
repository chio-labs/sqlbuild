"""Helpers for compile command performance guard tests."""

from __future__ import annotations

import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
from bisect import bisect_left
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from types import FrameType
from typing import Any, NamedTuple, cast

import pytest

from scripts.cold_compile_performance.main.read_compile_measurement import read_compile_measurement
from scripts.cold_compile_performance.main.semantic_compile_fingerprint import (
    semantic_compile_fingerprint,
)
from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    FreshProcessCompileCachePerformanceGuardTestCase,
)

_DBT_SHAPED_SQL_SIZE_PROFILE: tuple[tuple[float, int], ...] = (
    (0.50, 1_800),
    (0.75, 4_500),
    (0.90, 8_000),
    (0.95, 12_500),
    (0.99, 20_000),
    (0.992, 50_000),
    (0.994, 175_000),
    (0.999, 265_000),
    (1.0, 522_000),
)
_DBT_SHAPED_WARM_SAMPLE_COUNT: int = 3
_PERFORMANCE_SAFETY_TIMEOUT_MULTIPLIER: float = 2.0


class CompileBenchmarkMeasurement(NamedTuple):
    elapsed_seconds: float
    timings_ms: dict[str, int]
    summary: dict[str, int]


def nested_coalesce_expression(*, function_depth: int) -> str:
    expression: str = "1"
    for _ in range(function_depth):
        expression = f"COALESCE({expression}, 0)"
    return expression


class LayeredProductionCompileBenchmarkResult(NamedTuple):
    cold: CompileBenchmarkMeasurement
    warm: CompileBenchmarkMeasurement
    leaf_model_edit: CompileBenchmarkMeasurement
    central_model_edit: CompileBenchmarkMeasurement
    test_edit: CompileBenchmarkMeasurement
    macro_edit: CompileBenchmarkMeasurement
    project_config_edit: CompileBenchmarkMeasurement


class SemanticCompileBenchmarkResult(NamedTuple):
    cold: CompileBenchmarkMeasurement
    warm: CompileBenchmarkMeasurement


class FreshProcessCompileBenchmarkResult(NamedTuple):
    elapsed_seconds: float
    peak_rss_bytes: int
    semantic_fingerprint: str
    payload: dict[str, object]
    cpu_seconds: float
    major_page_faults: int
    minor_page_faults: int

    def __repr__(self) -> str:
        return (
            f"FreshProcessCompileBenchmarkResult(elapsed_seconds={self.elapsed_seconds}, "
            f"cpu_seconds={self.cpu_seconds}, peak_rss_bytes={self.peak_rss_bytes}, "
            f"major_page_faults={self.major_page_faults}, "
            f"minor_page_faults={self.minor_page_faults}, "
            f"semantic_fingerprint={self.semantic_fingerprint!r}, "
            f"compile_timings={self.payload.get('compile_timings')!r})"
        )


class FreshProcessCompileCacheBenchmarkResult(NamedTuple):
    cold: FreshProcessCompileBenchmarkResult
    warm: FreshProcessCompileBenchmarkResult
    leaf_edit: FreshProcessCompileBenchmarkResult
    after_leaf_edit: FreshProcessCompileBenchmarkResult
    macro_edit: FreshProcessCompileBenchmarkResult
    after_macro_edit: FreshProcessCompileBenchmarkResult
    project_config_edit: FreshProcessCompileBenchmarkResult
    after_project_config_edit: FreshProcessCompileBenchmarkResult
    cache_bytes: int


def fresh_process_compile_cache_metrics(
    measurement: FreshProcessCompileBenchmarkResult,
) -> tuple[int, int, int, int]:
    """Return semantic analysis cache counters from one compile result."""

    timings: object = measurement.payload["compile_timings"]
    assert isinstance(timings, dict)
    timings_by_name: dict[str, object] = {str(key): value for key, value in timings.items()}

    def metric(name: str) -> int:
        value: object = timings_by_name.get(name)
        assert type(value) is int
        return value

    return (
        metric("analysis_batch_cache_hits"),
        metric("analysis_entry_cache_hits"),
        metric("analysis_cache_misses"),
        metric("analysis_cache_bypasses"),
    )


def assert_complete_compile_cache_hit(
    *, measurement: FreshProcessCompileBenchmarkResult, model_count: int
) -> None:
    """Assert every model was served by one of the analysis cache layers."""

    batch_hits, entry_hits, misses, bypasses = fresh_process_compile_cache_metrics(measurement)
    assert batch_hits + entry_hits == model_count
    assert misses == 0
    assert bypasses == 0


def assert_successful_compile_cache_payload(
    *,
    measurement: FreshProcessCompileBenchmarkResult,
    test_case: FreshProcessCompileCachePerformanceGuardTestCase,
) -> None:
    """Assert exact representative resource counts and clean diagnostics."""

    assert measurement.payload["has_errors"] is False
    assert measurement.payload["diagnostics"] == []
    assert measurement.payload["summary"] == {
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


class DbtShapedCompileBenchmarkResult(NamedTuple):
    cold_seconds: float
    warm_median_seconds: float
    warm_samples_seconds: tuple[float, ...]


def run_advanced_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    expected_max_seconds: float,
    scan_event_lines_per_model: int = 0,
) -> float:
    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()

    write_advanced_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        scan_event_lines_per_model=scan_event_lines_per_model,
    )
    return _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_max_seconds,
    )


def run_dbt_shaped_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    expected_max_seconds: float,
    expected_warm_max_seconds: float,
) -> DbtShapedCompileBenchmarkResult:
    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    write_dbt_shaped_compile_project(project_dir=project_dir, model_count=model_count)
    cold_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_max_seconds * _PERFORMANCE_SAFETY_TIMEOUT_MULTIPLIER,
    )
    warm_safety_timeout: float = expected_warm_max_seconds * _PERFORMANCE_SAFETY_TIMEOUT_MULTIPLIER
    _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=warm_safety_timeout,
    )
    warm_samples: tuple[float, ...] = tuple(
        _run_compile_benchmark(
            project_dir=project_dir,
            expected_max_seconds=warm_safety_timeout,
        )
        for _ in range(_DBT_SHAPED_WARM_SAMPLE_COUNT)
    )
    return DbtShapedCompileBenchmarkResult(
        cold_seconds=cold_seconds,
        warm_median_seconds=statistics.median(warm_samples),
        warm_samples_seconds=warm_samples,
    )


def run_test_heavy_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    test_count: int,
    chain_depth: int,
    fixture_row_count: int,
    expected_max_seconds: float,
    expected_warm_max_seconds: float,
    expected_edit_max_seconds: float,
) -> tuple[float, float, float, float]:
    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    write_test_heavy_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        test_count=test_count,
        chain_depth=chain_depth,
        fixture_row_count=fixture_row_count,
    )
    cold_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_max_seconds,
    )
    warm_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_warm_max_seconds,
    )
    _append_benchmark_edit(project_dir / "models" / "model_00000.sql", "model")
    model_edit_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    _append_benchmark_edit(project_dir / "tests" / "unit" / "test_00000.sql", "test")
    test_edit_seconds: float = _run_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    return cold_seconds, warm_seconds, model_edit_seconds, test_edit_seconds


def run_layered_production_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    expected_cold_max_seconds: float,
    expected_warm_max_seconds: float,
    expected_edit_max_seconds: float,
    expected_config_edit_max_seconds: float,
) -> LayeredProductionCompileBenchmarkResult:
    """Measure the production-shaped cold, warm, and representative edit paths."""

    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    warmup_dir: Path = project_dir.parent / "compile_runtime_warmup"
    write_advanced_compile_project(project_dir=warmup_dir, model_count=32)
    _ = _run_compile_benchmark(project_dir=warmup_dir, expected_max_seconds=5.0)
    write_layered_production_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        test_count=test_count,
        audit_count=_REPRESENTATIVE_AUDIT_COUNT,
    )
    cold: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_cold_max_seconds,
    )
    warm: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_warm_max_seconds,
    )
    _append_benchmark_edit(_generated_model_path(project_dir, model_count - 1), "leaf model")
    leaf_model_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    _append_benchmark_edit(_generated_model_path(project_dir, 0), "central model")
    central_model_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    _append_benchmark_edit(
        project_dir / "tests" / "unit" / "test_group_00000.sql",
        "test",
    )
    test_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    macro_path: Path = project_dir / "macros" / "macro_00000.py"
    _replace_benchmark_text(
        path=macro_path,
        old='return f"({expression} + 0)"',
        new='return f"({expression} + 1000)"',
    )
    macro_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_edit_max_seconds,
    )
    config_path: Path = project_dir / "sqlbuild_project.toml"
    _replace_benchmark_text(
        path=config_path,
        old='benchmark_revision = "0"',
        new='benchmark_revision = "1"',
    )
    project_config_edit: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_config_edit_max_seconds,
    )
    return LayeredProductionCompileBenchmarkResult(
        cold=cold,
        warm=warm,
        leaf_model_edit=leaf_model_edit,
        central_model_edit=central_model_edit,
        test_edit=test_edit,
        macro_edit=macro_edit,
        project_config_edit=project_config_edit,
    )


def run_semantic_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    audit_count: int,
    expected_cold_max_seconds: float,
    expected_warm_max_seconds: float,
) -> SemanticCompileBenchmarkResult:
    """Measure cold and unchanged compiles for a semantically dense generated project."""

    skip_actions: dict[bool, Callable[[], None]] = {
        False: _continue_compile_benchmark,
        True: _skip_compile_benchmark,
    }
    skip_actions[os.environ.get("SQLBUILD_SKIP_PERFORMANCE_TESTS") == "1"]()
    warmup_dir: Path = project_dir.parent / "semantic_compile_runtime_warmup"
    write_advanced_compile_project(project_dir=warmup_dir, model_count=32)
    _ = _run_compile_benchmark(project_dir=warmup_dir, expected_max_seconds=5.0)
    write_semantic_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        test_count=test_count,
        audit_count=audit_count,
    )
    cold: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_cold_max_seconds,
    )
    warm: CompileBenchmarkMeasurement = _run_profiled_compile_benchmark(
        project_dir=project_dir,
        expected_max_seconds=expected_warm_max_seconds,
    )
    return SemanticCompileBenchmarkResult(cold=cold, warm=warm)


def run_fresh_process_semantic_compile_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    audit_count: int,
    expected_max_wall_seconds: float,
) -> FreshProcessCompileBenchmarkResult:
    """Compile one clean semantic fixture in a fresh process without compiler caches."""

    write_semantic_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        test_count=test_count,
        audit_count=audit_count,
    )
    target_dir: Path = project_dir / "target"
    assert not target_dir.exists()
    result: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"fresh-process-{model_count}",
        expected_max_wall_seconds=expected_max_wall_seconds,
        compile_args=("--no-cache",),
    )
    assert not (target_dir / "cache").exists()
    return result


def run_fresh_process_compile_cache_benchmark(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    audit_count: int,
    expected_cold_max_wall_seconds: float,
    expected_warm_max_wall_seconds: float,
    expected_edit_max_wall_seconds: float,
    macro_call_interval: int,
    scoped_macros: bool,
) -> FreshProcessCompileCacheBenchmarkResult:
    """Measure exact and incremental cache reuse across independent CLI processes."""

    write_semantic_compile_project(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        test_count=test_count,
        audit_count=audit_count,
        macro_call_interval=macro_call_interval,
        scoped_macros=scoped_macros,
    )
    target_dir: Path = project_dir / "target"
    assert not target_dir.exists()
    cold: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-cold-{model_count}",
        expected_max_wall_seconds=expected_cold_max_wall_seconds,
        compile_args=(),
    )
    warm: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-warm-{model_count}",
        expected_max_wall_seconds=expected_warm_max_wall_seconds,
        compile_args=(),
    )
    _append_benchmark_edit(_generated_model_path(project_dir, model_count - 1), "leaf model")
    leaf_edit: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-leaf-edit-{model_count}",
        expected_max_wall_seconds=expected_edit_max_wall_seconds,
        compile_args=(),
    )
    after_leaf_edit: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-after-leaf-edit-{model_count}",
        expected_max_wall_seconds=expected_warm_max_wall_seconds,
        compile_args=(),
    )
    macro_path: Path = next(project_dir.rglob("macro_00000.py"))
    _replace_benchmark_text(
        path=macro_path,
        old='return f"({expression} + 1)"',
        new='return f"({expression} + 1000)"',
    )
    macro_edit: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-macro-edit-{model_count}",
        expected_max_wall_seconds=expected_edit_max_wall_seconds,
        compile_args=(),
    )
    after_macro_edit: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-after-macro-edit-{model_count}",
        expected_max_wall_seconds=expected_warm_max_wall_seconds,
        compile_args=(),
    )
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    _replace_benchmark_text(
        path=project_config_path,
        old='benchmark_revision = "0"',
        new='benchmark_revision = "1"',
    )
    project_config_edit: FreshProcessCompileBenchmarkResult = _run_fresh_process_compile_benchmark(
        project_dir=project_dir,
        label=f"cache-project-config-edit-{model_count}",
        expected_max_wall_seconds=expected_cold_max_wall_seconds,
        compile_args=(),
    )
    after_project_config_edit: FreshProcessCompileBenchmarkResult = (
        _run_fresh_process_compile_benchmark(
            project_dir=project_dir,
            label=f"cache-after-project-config-edit-{model_count}",
            expected_max_wall_seconds=expected_warm_max_wall_seconds,
            compile_args=(),
        )
    )
    cache_dir: Path = target_dir / "cache" / "compiler"
    cache_bytes: int = sum(path.stat().st_size for path in cache_dir.rglob("*.json")) + sum(
        path.stat().st_size for path in cache_dir.rglob("*.sqlite3")
    )
    return FreshProcessCompileCacheBenchmarkResult(
        cold=cold,
        warm=warm,
        leaf_edit=leaf_edit,
        after_leaf_edit=after_leaf_edit,
        macro_edit=macro_edit,
        after_macro_edit=after_macro_edit,
        project_config_edit=project_config_edit,
        after_project_config_edit=after_project_config_edit,
        cache_bytes=cache_bytes,
    )


def _run_fresh_process_compile_benchmark(
    *,
    project_dir: Path,
    label: str,
    expected_max_wall_seconds: float,
    compile_args: tuple[str, ...],
) -> FreshProcessCompileBenchmarkResult:
    measurement_path: Path = project_dir.parent / f"{label}-measurement.txt"
    output_path: Path = project_dir.parent / f"{label}.json"
    stderr_path: Path = project_dir.parent / f"{label}.stderr"
    command: list[str] = [
        "/usr/bin/time",
        "--quiet",
        "--output",
        str(measurement_path),
        "--format",
        "%e %M %U %S %F %R",
        str(Path(sys.executable).with_name("sqb")),
        "--project-dir",
        str(project_dir),
        "--no-color",
        "compile",
        "--json",
        *compile_args,
    ]
    started: float = time.monotonic()
    try:
        with (
            output_path.open("wb") as output_file,
            stderr_path.open("wb") as stderr_file,
        ):
            with subprocess.Popen(
                command,
                stdout=output_file,
                stderr=stderr_file,
                start_new_session=True,
            ) as process:
                try:
                    returncode: int = process.wait(timeout=expected_max_wall_seconds + 10.0)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise
    finally:
        payload_object, measurement = read_compile_measurement(
            label=label,
            measurement_path=measurement_path,
            output_path=output_path,
            elapsed_seconds=time.monotonic() - started,
        )
    assert returncode == 0, stderr_path.read_text(encoding="utf-8")
    elapsed_text, peak_rss_kib_text, user_text, system_text, major_text, minor_text = measurement
    elapsed_seconds: float = float(elapsed_text)
    assert isinstance(payload_object, dict)
    payload: dict[str, object] = cast(dict[str, object], payload_object)
    peak_rss_bytes: int = int(peak_rss_kib_text) * 1024
    compiled_dir: Path = project_dir / "target" / "compiled"
    semantic_fingerprint: str = semantic_compile_fingerprint(
        payload=payload, compiled_dir=compiled_dir
    )
    return FreshProcessCompileBenchmarkResult(
        elapsed_seconds=elapsed_seconds,
        peak_rss_bytes=peak_rss_bytes,
        semantic_fingerprint=semantic_fingerprint,
        payload=payload,
        cpu_seconds=float(user_text) + float(system_text),
        major_page_faults=int(major_text),
        minor_page_faults=int(minor_text),
    )


def _append_benchmark_edit(path: Path, label: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n-- one {label} edit\n",
        encoding="utf-8",
    )


def _replace_benchmark_text(*, path: Path, old: str, new: str) -> None:
    contents: str = path.read_text(encoding="utf-8")
    _ = contents.index(old)
    path.write_text(contents.replace(old, new, 1), encoding="utf-8")


def _run_compile_benchmark(*, project_dir: Path, expected_max_seconds: float) -> float:
    with _fail_after_seconds(expected_max_seconds):
        start: float = time.perf_counter()
        exit_code: int = main(
            [
                "--project-dir",
                str(project_dir),
                "--no-color",
                "compile",
            ]
        )
        elapsed_seconds: float = time.perf_counter() - start
    assert exit_code == 0
    return elapsed_seconds


def _run_profiled_compile_benchmark(
    *, project_dir: Path, expected_max_seconds: float
) -> CompileBenchmarkMeasurement:
    output: StringIO = StringIO()
    diagnostic_grace_seconds: float = 5.0
    with (
        _fail_after_seconds(expected_max_seconds + diagnostic_grace_seconds),
        redirect_stdout(output),
    ):
        start: float = time.perf_counter()
        exit_code: int = main(
            [
                "--project-dir",
                str(project_dir),
                "--no-color",
                "compile",
                "--json",
            ]
        )
        elapsed_seconds: float = time.perf_counter() - start
    assert exit_code == 0, output.getvalue()
    payload: dict[str, object] = json.loads(output.getvalue())
    timings: object = payload["compile_timings"]
    summary: object = payload["summary"]
    assert isinstance(timings, dict)
    assert isinstance(summary, dict)
    return CompileBenchmarkMeasurement(
        elapsed_seconds=elapsed_seconds,
        timings_ms={str(key): int(value) for key, value in timings.items()},
        summary={str(key): int(value) for key, value in summary.items()},
    )


def _generated_model_path(project_dir: Path, index: int) -> Path:
    layer_index: int = index % 10
    folder: str = {
        (True, True): "staging",
        (False, True): "intermediate",
        (False, False): "mart",
    }[(layer_index < 4, layer_index < 8)]
    return project_dir / "models" / folder / f"model_{index:05d}.sql"


def measure_model_sql_bytes(project_dir: Path) -> int:
    return sum(path.stat().st_size for path in (project_dir / "models").rglob("*.sql"))


def measure_compiled_test_sql_bytes(project_dir: Path) -> int:
    compiled_tests_dir: Path = project_dir / "target" / "compiled" / "tests"
    return sum(path.stat().st_size for path in compiled_tests_dir.rglob("*.sql"))


def measure_declared_model_columns(project_dir: Path) -> int:
    return sum(
        path.read_text(encoding="utf-8").count("(type ")
        for path in (project_dir / "models").rglob("*.sql")
    )


@contextmanager
def _fail_after_seconds(seconds: float) -> Iterator[None]:
    def _raise_timeout(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        raise TimeoutError(f"compile benchmark exceeded {seconds:.1f}s budget")

    previous_handler: Any = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous_handler)


def write_advanced_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    scan_event_lines_per_model: int = 0,
) -> None:
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    _write_compile_project_config(project_dir)
    base_model_sql: str = _with_reference_scan_workload(
        sql=_base_model_sql(),
        model_index=0,
        scan_event_lines=scan_event_lines_per_model,
    )
    (models_dir / "model_00000.sql").write_text(base_model_sql, encoding="utf-8")
    for index in range(1, model_count):
        model_sql: str = _with_reference_scan_workload(
            sql=_chain_model_sql(index=index),
            model_index=index,
            scan_event_lines=scan_event_lines_per_model,
        )
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")


def write_dbt_shaped_compile_project(*, project_dir: Path, model_count: int) -> None:
    models_dir: Path = project_dir / "models"
    models_dir.mkdir(parents=True)
    _write_compile_project_config(project_dir)
    base_model_sql: str = _with_base_generated_logic(
        sql=_base_model_sql(),
        target_bytes=_sql_size_target(model_index=0, model_count=model_count),
    )
    (models_dir / "model_00000.sql").write_text(base_model_sql, encoding="utf-8")
    for index in range(1, model_count):
        model_sql: str = _with_chain_generated_logic(
            sql=_chain_model_sql(index=index),
            target_bytes=_sql_size_target(model_index=index, model_count=model_count),
        )
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")


def write_test_heavy_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    test_count: int,
    chain_depth: int,
    fixture_row_count: int,
) -> None:
    models_dir: Path = project_dir / "models"
    tests_dir: Path = project_dir / "tests" / "unit"
    models_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    _write_compile_project_config(project_dir)
    for index in range(model_count):
        group_offset: int = index % chain_depth
        model_sql_builder: Callable[..., str] = {
            True: _test_heavy_base_model_sql,
            False: _test_heavy_chain_model_sql,
        }[group_offset == 0]
        model_sql: str = model_sql_builder(index=index)
        (models_dir / f"model_{index:05d}.sql").write_text(model_sql, encoding="utf-8")
    group_count: int = model_count // chain_depth
    for test_index in range(test_count):
        cases_per_target: int = 5
        group_index: int = (test_index // cases_per_target) % group_count
        base_index: int = group_index * chain_depth
        target_index: int = base_index + chain_depth - 1
        test_sql: str = _test_heavy_sql(
            base_index=base_index,
            target_index=target_index,
            fixture_row_count=fixture_row_count,
        )
        (tests_dir / f"test_{test_index:05d}.sql").write_text(test_sql, encoding="utf-8")


def _write_compile_project_config(project_dir: Path) -> None:
    (project_dir / "sqlbuild_project.toml").write_text(
        "\n".join(
            (
                'name = "performance_guard"',
                'adapter = "duckdb"',
                'default_target = "dev"',
                "",
                "[connection]",
                'database = ":memory:"',
                "",
                "[targets.dev]",
                'schema = "main"',
                "",
            )
        ),
        encoding="utf-8",
    )


def _continue_compile_benchmark() -> None:
    return None


def _skip_compile_benchmark() -> None:
    pytest.skip("SQLBUILD_SKIP_PERFORMANCE_TESTS=1")


def _with_reference_scan_workload(*, sql: str, model_index: int, scan_event_lines: int) -> str:
    comments: str = "".join(
        f"-- generated mapping {line:05d}: source='source_{model_index:05d}' "
        f"expression=__not_a_reference_{line:05d}\n"
        for line in range(scan_event_lines)
    )
    header_end: int = sql.index(";\n") + 2
    return f"{sql[:header_end]}{comments}{sql[header_end:]}"


def _sql_size_target(*, model_index: int, model_count: int) -> int:
    quantile: float = (model_index + 1) / model_count
    upper_quantiles: tuple[float, ...] = tuple(item[0] for item in _DBT_SHAPED_SQL_SIZE_PROFILE)
    target_sizes: tuple[int, ...] = tuple(item[1] for item in _DBT_SHAPED_SQL_SIZE_PROFILE)
    return target_sizes[bisect_left(upper_quantiles, quantile)]


def _generated_case_logic(*, sql: str, target_bytes: int) -> str:
    missing_bytes: int = max(0, target_bytes - len(sql.encode("utf-8")))
    clause_template: str = "      WHEN id = 00000 THEN 'segment_00000'\n"
    clause_count: int = (missing_bytes + len(clause_template) - 1) // len(clause_template)
    clauses: str = "".join(
        f"      WHEN id = {index:05d} THEN 'segment_{index:05d}'\n" for index in range(clause_count)
    )
    return f"    CASE\n{clauses}      ELSE 'unmatched'\n    END AS generated_mapping"


def _with_base_generated_logic(*, sql: str, target_bytes: int) -> str:
    header, query = sql.split(";\n", 1)
    generated_logic: str = _generated_case_logic(sql=sql, target_bytes=target_bytes)
    return f"""{header};
WITH base AS (
{query.rstrip()}
),
generated_logic AS (
  SELECT
    *,
{generated_logic}
  FROM base
)
SELECT id, bucket, amount, avg_amount, max_amount, status
FROM generated_logic
"""


def _with_chain_generated_logic(*, sql: str, target_bytes: int) -> str:
    generated_logic: str = _generated_case_logic(sql=sql, target_bytes=target_bytes)
    widened_sql: str = sql.replace(
        ")\nSELECT\n  id,",
        f"""),
generated_logic AS (
  SELECT
    *,
{generated_logic}
  FROM joined
)
SELECT
  id,""",
        1,
    )
    prefix, suffix = widened_sql.rsplit("\nFROM joined", 1)
    return f"{prefix}\nFROM generated_logic{suffix}"


def _base_model_sql() -> str:
    return "\n".join(
        (
            "MODEL (materialized view);",
            "",
            "SELECT",
            "  0 AS id,",
            "  'even' AS bucket,",
            "  CAST(1 AS DOUBLE) AS amount,",
            "  CAST(1 AS DOUBLE) AS avg_amount,",
            "  CAST(1 AS DOUBLE) AS max_amount,",
            "  'small' AS status",
            "",
        )
    )


def _chain_model_sql(*, index: int) -> str:
    previous_model: str = f"model_{index - 1:05d}"
    return f'''MODEL (materialized view);

WITH base AS (
  SELECT
    id + 1 AS id,
    bucket,
    CAST(amount AS DOUBLE) AS amount,
    CAST(avg_amount AS DOUBLE) AS avg_amount,
    CAST(max_amount AS DOUBLE) AS max_amount,
    status
  FROM __ref("{previous_model}")
),
windowed AS (
  SELECT
    id,
    CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS bucket,
    amount + avg_amount AS amount,
    LAG(amount, 1, 0) OVER (ORDER BY id) AS previous_amount,
    SUM(amount) OVER (
      PARTITION BY bucket
      ORDER BY id
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount,
    ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY id) AS row_number
  FROM base
),
grouped AS (
  SELECT
    bucket,
    AVG(amount) AS avg_amount,
    MAX(running_amount) AS max_amount,
    COUNT(*) AS row_count
  FROM windowed
  GROUP BY bucket
),
joined AS (
  SELECT
    w.id,
    w.bucket,
    w.amount + COALESCE(w.previous_amount, 0) AS amount,
    g.avg_amount,
    g.max_amount,
    CASE
      WHEN g.row_count > 10 THEN 'large'
      WHEN w.amount > g.avg_amount THEN 'above_average'
      ELSE 'small'
    END AS status
  FROM windowed w
  JOIN grouped g
    ON w.bucket = g.bucket
  WHERE w.row_number >= 1
)
SELECT
  id,
  bucket,
  amount,
  avg_amount,
  max_amount,
  status
FROM joined
'''


def _test_heavy_base_model_sql(*, index: int) -> str:
    return f"""MODEL (materialized view);

SELECT
  {index} AS id,
  CAST({index} AS DOUBLE) AS amount,
  'base' AS status
"""


def _test_heavy_chain_model_sql(*, index: int) -> str:
    previous_model: str = f"model_{index - 1:05d}"
    return f'''MODEL (materialized view);

WITH transformed AS (
  SELECT
    id + 1 AS id,
    amount + {index} AS amount,
    CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS status
  FROM __ref("{previous_model}")
),
windowed AS (
  SELECT
    id,
    amount,
    status,
    ROW_NUMBER() OVER (PARTITION BY status ORDER BY id) AS row_number,
    SUM(amount) OVER (PARTITION BY status ORDER BY id) AS running_amount
  FROM transformed
)
SELECT id, amount + running_amount AS amount, status
FROM windowed
WHERE row_number >= 1
'''


def _test_heavy_sql(*, base_index: int, target_index: int, fixture_row_count: int) -> str:
    fixture_rows: str = " UNION ALL\n".join(
        f"  SELECT {row} AS id, CAST({row} AS DOUBLE) AS amount, 'base' AS status"
        for row in range(fixture_row_count)
    )
    return f"""TEST();

WITH
__ref__model_{base_index:05d} AS (
{fixture_rows}
),
__expected__model_{target_index:05d} AS (
  SELECT 1 AS id, CAST(1 AS DOUBLE) AS amount, 'odd' AS status
)
SELECT 1
"""


_SPINE_DEPTH: int = 54
_TEST_CHAIN_DEPTH: int = 8
_REPRESENTATIVE_AUDIT_COUNT: int = 700
_TOP_LEVEL_WITH_INTERVAL: int = 20
_NESTED_QUERY_INTERVAL: int = 15
_MACRO_INTERVAL: int = 13
_BENCHMARK_MACRO_CALL: re.Pattern[str] = re.compile(r"@(macro_\d{5})\(")
_FUNCTION_INTERVAL: int = 43
_SEED_INTERVAL: int = 67
_SEED_REFERENCE_START_INDEX: int = 300
_SQL_SIZE_PROFILE: tuple[tuple[float, int], ...] = (
    (0.0, 400),
    (0.50, 1_900),
    (0.75, 4_500),
    (0.90, 11_000),
    (0.95, 15_200),
    (0.99, 48_200),
    (0.995, 120_000),
    (0.999, 260_000),
    (1.0, 520_000),
)
_SEMANTIC_COLUMN_COUNT_PROFILE: tuple[tuple[float, int], ...] = (
    (0.0, 3),
    (0.25, 9),
    (0.50, 19),
    (0.75, 33),
    (0.90, 58),
    (0.95, 115),
    (0.99, 232),
    (1.0, 538),
)
_SEMANTIC_SET_OPERATION_MODEL_INDEX: int = _SPINE_DEPTH
_SEMANTIC_SET_OPERATION_BRANCH_COUNT: int = 267


def write_layered_production_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    audit_count: int,
) -> None:
    """Write a deterministic generated project matching real resource ratios."""

    _layered_write_project_config(project_dir=project_dir)
    _layered_write_sources(project_dir=project_dir, source_count=source_count)
    _layered_write_seeds(project_dir=project_dir, seed_count=seed_count)
    _layered_write_functions(project_dir=project_dir, function_count=function_count)
    _layered_write_macros(project_dir=project_dir, macro_count=macro_count)
    _layered_write_schemas(project_dir=project_dir)
    _layered_write_hooks(project_dir=project_dir)
    _layered_write_models(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        audit_count=audit_count,
    )
    _layered_write_tests(
        project_dir=project_dir,
        model_count=model_count,
        test_count=test_count,
        source_count=source_count,
        seed_count=seed_count,
    )


def write_semantic_compile_project(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    test_count: int,
    audit_count: int,
    macro_call_interval: int = _MACRO_INTERVAL,
    scoped_macros: bool = False,
) -> None:
    """Write a neutral project with broad resources and dense SQL semantics."""

    _layered_write_project_config(project_dir=project_dir)
    _layered_write_sources(project_dir=project_dir, source_count=source_count)
    _layered_write_seeds(project_dir=project_dir, seed_count=seed_count)
    _layered_write_functions(project_dir=project_dir, function_count=function_count)
    _layered_write_macros(project_dir=project_dir, macro_count=macro_count)
    _layered_write_hooks(project_dir=project_dir)
    _semantic_write_models(
        project_dir=project_dir,
        model_count=model_count,
        source_count=source_count,
        seed_count=seed_count,
        function_count=function_count,
        macro_count=macro_count,
        audit_count=audit_count,
        macro_call_interval=macro_call_interval,
    )
    {True: _scope_single_folder_macros, False: _keep_project_macros}[scoped_macros](
        project_dir=project_dir
    )
    _layered_write_tests(
        project_dir=project_dir,
        model_count=model_count,
        test_count=test_count,
        source_count=source_count,
        semantic_fixture_scale=True,
        seed_count=seed_count,
    )


def _layered_write_project_config(*, project_dir: Path) -> None:
    project_dir.mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        """name = "layered_production_performance_guard"
adapter = "duckdb"
default_target = "dev"

[settings]
column_contract_mode = "explicit"

[vars]
benchmark_revision = "0"

[targets.dev]
schema = "main"

[path_defaults."staging"]
materialized = "view"

[path_defaults."intermediate"]
materialized = "table"

[path_defaults."mart"]
materialized = "table"
""",
        encoding="utf-8",
    )


def _layered_write_sources(*, project_dir: Path, source_count: int) -> None:
    sources_dir: Path = project_dir / "sources"
    sources_dir.mkdir()
    entries: str = "\n".join(
        f"""  - name: source_{index:05d}
    expression: "(SELECT {index} AS id, CAST({index} AS DOUBLE) AS amount, 'source' AS status)"
    columns:
      - name: id
        type: INTEGER
      - name: amount
        type: DOUBLE
      - name: status
        type: VARCHAR"""
        for index in range(source_count)
    )
    (sources_dir / "generated.yml").write_text(f"sources:\n{entries}\n", encoding="utf-8")


def _layered_write_seeds(*, project_dir: Path, seed_count: int) -> None:
    seeds_dir: Path = project_dir / "seeds"
    seeds_dir.mkdir()
    schema_entries: str = "\n".join(
        f"""  - name: seed_{index:05d}
    columns:
      - name: id
        type: INTEGER
      - name: label
        type: VARCHAR"""
        for index in range(seed_count)
    )
    (seeds_dir / "generated.yml").write_text(f"seeds:\n{schema_entries}\n", encoding="utf-8")
    for index in range(seed_count):
        (seeds_dir / f"seed_{index:05d}.csv").write_text(
            f"id,label\n{index},seed_{index:05d}\n",
            encoding="utf-8",
        )


def _layered_write_functions(*, project_dir: Path, function_count: int) -> None:
    functions_dir: Path = project_dir / "functions" / "sql"
    functions_dir.mkdir(parents=True)
    for index in range(function_count):
        (functions_dir / f"fn_{index:05d}.sql").write_text(
            """FUNCTION (
  arguments (input_value DOUBLE),
  returns DOUBLE,
);

input_value + 1
""",
            encoding="utf-8",
        )


def _layered_write_macros(*, project_dir: Path, macro_count: int) -> None:
    macros_dir: Path = project_dir / "macros"
    macros_dir.mkdir(parents=True)
    for index in range(macro_count):
        composed_dependency: str = {
            True: (
                '\n\ndef base_offset(expression: str) -> str:\n    return f"({expression} + 1)"\n'
            ),
            False: "",
        }[index == 0]
        macro_body: str = {
            True: "    return base_offset(_offset(expression))",
            False: "    return _offset(expression)",
        }[index == 0]
        (macros_dir / f"macro_{index:05d}.py").write_text(
            f"""def _offset(expression: str) -> str:
    return f"({{expression}} + {index})"
{composed_dependency}


def macro_{index:05d}(expression: str) -> str:
{macro_body}
""",
            encoding="utf-8",
        )


def _keep_project_macros(*, project_dir: Path) -> None:
    """Leave generated macros in the project-wide macro directory."""


def _scope_single_folder_macros(*, project_dir: Path) -> None:
    """Move each macro beside its only consuming folder and drop unused macros."""

    consumer_folders: dict[str, set[str]] = {}
    for model_path in sorted((project_dir / "models").rglob("*.sql")):
        for call in _BENCHMARK_MACRO_CALL.findall(model_path.read_text(encoding="utf-8")):
            consumer_folders.setdefault(call, set()).add(model_path.parent.name)
    macros_dir: Path = project_dir / "macros"
    generated: set[str] = {path.stem for path in macros_dir.glob("macro_*.py")}
    for unused_stem in sorted(generated - set(consumer_folders)):
        (macros_dir / f"{unused_stem}.py").unlink()
    assert all(len(folders) == 1 for folders in consumer_folders.values())
    for stem, folders in sorted(consumer_folders.items()):
        (folder,) = folders
        scoped_dir: Path = project_dir / "models" / folder / "_sqlbuild" / "_macros"
        scoped_dir.mkdir(parents=True, exist_ok=True)
        (macros_dir / f"{stem}.py").rename(scoped_dir / f"{stem}.py")


def _layered_write_schemas(*, project_dir: Path) -> None:
    schemas_dir: Path = project_dir / "schemas"
    schemas_dir.mkdir()
    (schemas_dir / "benchmark_row.sql").write_text(
        """SCHEMA (
  name benchmark_row,
  columns (
    id (type INTEGER, nullable false),
    amount (type DOUBLE),
    status (type VARCHAR),
  ),
);
""",
        encoding="utf-8",
    )


def _layered_write_hooks(*, project_dir: Path) -> None:
    hooks_dir: Path = project_dir / "hooks" / "sql"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "before_build.sql").write_text(
        'HOOK (description "Generated pre-build hook");\n\nSELECT 1\n',
        encoding="utf-8",
    )
    (hooks_dir / "after_build.sql").write_text(
        'HOOK (description "Generated post-build hook");\n\nSELECT 2\n',
        encoding="utf-8",
    )


def _layered_write_models(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    audit_count: int,
) -> None:
    for index in range(model_count):
        folder: str = _layered_model_folder(index=index)
        model_dir: Path = project_dir / "models" / folder
        model_dir.mkdir(parents=True, exist_ok=True)
        sql: str = _layered_model_sql(
            index=index,
            model_count=model_count,
            source_count=source_count,
            audit_count=audit_count,
            seed_count=seed_count,
            function_count=function_count,
            macro_count=macro_count,
        )
        (model_dir / f"model_{index:05d}.sql").write_text(sql, encoding="utf-8")


def _layered_model_folder(*, index: int) -> str:
    layer_index: int = index % 10
    return {
        (True, True): "staging",
        (False, True): "intermediate",
        (False, False): "mart",
    }[(layer_index < 4, layer_index < 8)]


def _layered_is_base_model(*, index: int) -> bool:
    return index == 0 or (index >= _SPINE_DEPTH and (index - _SPINE_DEPTH) % _TEST_CHAIN_DEPTH == 0)


def _layered_model_header(*, index: int, audit_count: int) -> str:
    contract_header: str = """MODEL (
  model_schema benchmark_row,
  contract enforced,
  columns (
    id (audits [not_null]),
  ),
);"""
    audit_header: str = """MODEL (
  columns (
    id (nullable false, audits [not_null]),
  ),
);"""
    return {
        (True, False): contract_header,
        (False, True): "MODEL ();",
        (False, False): audit_header,
    }[(index == 0, index >= audit_count)]


def _layered_model_sql(
    *,
    index: int,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    audit_count: int,
) -> str:
    builders: dict[bool, Callable[[], str]] = {
        True: lambda: _layered_base_model_sql(
            index=index,
            model_count=model_count,
            source_count=source_count,
            audit_count=audit_count,
        ),
        False: lambda: _layered_dependent_model_sql(
            index=index,
            model_count=model_count,
            seed_count=seed_count,
            function_count=function_count,
            macro_count=macro_count,
            audit_count=audit_count,
        ),
    }
    return builders[_layered_is_base_model(index=index)]()


def _layered_base_model_sql(
    *, index: int, model_count: int, source_count: int, audit_count: int
) -> str:
    source_index: int = _layered_base_source_index(index=index, source_count=source_count)
    contract_query_sql: str = f"""{_layered_model_header(index=index, audit_count=audit_count)}

SELECT
  CAST(id AS INTEGER) AS id,
  CAST(amount + CAST(@@benchmark_revision AS INTEGER) AS DOUBLE) AS amount,
  CAST(status AS VARCHAR) AS status
FROM __source("source_{source_index:05d}")
"""
    regular_query_sql: str = f"""{_layered_model_header(index=index, audit_count=audit_count)}

SELECT
  id,
  amount + {_layered_generated_mapping_expression()}
    + CAST(@@benchmark_revision AS INTEGER) AS amount,
  status
FROM __source("source_{source_index:05d}")
"""
    query_sql: str = {True: contract_query_sql, False: regular_query_sql}[index == 0]
    return _layered_pad_model_sql(
        sql=query_sql,
        target_bytes=_layered_model_sql_size_target(index=index, model_count=model_count),
        index=index,
    )


def _layered_dependent_model_sql(
    *,
    index: int,
    model_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    audit_count: int,
) -> str:
    previous_name: str = f"model_{index - 1:05d}"
    macro_index: int = (index // _MACRO_INTERVAL) % macro_count
    id_expression: str = {
        True: f'@macro_{macro_index:05d}("id")',
        False: f"id + {index % 7}",
    }[index % _MACRO_INTERVAL == 0]
    generated_amount_expression: str = (
        f"amount + {index % 11} + {_layered_generated_mapping_expression()} "
        "+ CAST(@@benchmark_revision AS INTEGER)"
    )
    function_index: int = index % function_count
    amount_expression: str = {
        True: f'__udf("fn_{function_index:05d}")(amount)',
        False: generated_amount_expression,
    }[index % _FUNCTION_INTERVAL == 0]
    seed_index: int = index % seed_count
    join_sql: str = {
        True: f'\nLEFT JOIN __seed("seed_{seed_index:05d}") AS seed ON seed.id = previous.id',
        False: "",
    }[index >= _SEED_REFERENCE_START_INDEX and index % _SEED_INTERVAL == 0]
    query: str = f'''SELECT
  {id_expression} AS id,
  {amount_expression} AS amount,
  CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS status
FROM __ref("{previous_name}") AS previous{join_sql}
'''
    direct_sql: str = f"{_layered_model_header(index=index, audit_count=audit_count)}\n\n{query}"
    with_sql: str = f"""{_layered_model_header(index=index, audit_count=audit_count)}

WITH transformed AS (
{query.rstrip()}
)
SELECT id, amount, status FROM transformed
"""
    nested_sql: str = f"""{_layered_model_header(index=index, audit_count=audit_count)}

SELECT id, amount, status
FROM (
{query.rstrip()}
) AS nested_query
"""
    model_sql: str = {
        (True, True): with_sql,
        (True, False): with_sql,
        (False, True): nested_sql,
        (False, False): direct_sql,
    }[
        (
            index % _TOP_LEVEL_WITH_INTERVAL == 0,
            index % _NESTED_QUERY_INTERVAL == 0,
        )
    ]
    return _layered_pad_model_sql(
        sql=model_sql,
        target_bytes=_layered_model_sql_size_target(index=index, model_count=model_count),
        index=index,
    )


def _semantic_write_models(
    *,
    project_dir: Path,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    audit_count: int,
    macro_call_interval: int = _MACRO_INTERVAL,
) -> None:
    for index in range(model_count):
        model_dir: Path = project_dir / "models" / _layered_model_folder(index=index)
        model_dir.mkdir(parents=True, exist_ok=True)
        column_count: int = _semantic_model_column_count(index=index, model_count=model_count)
        builders: dict[bool, Callable[[], str]] = {
            True: lambda index=index, column_count=column_count: _semantic_set_operation_model_sql(
                index=index,
                source_count=source_count,
                column_count=column_count,
                model_count=model_count,
                audit_count=audit_count,
            ),
            False: lambda index=index, column_count=column_count: _semantic_regular_model_sql(
                index=index,
                model_count=model_count,
                source_count=source_count,
                seed_count=seed_count,
                function_count=function_count,
                macro_count=macro_count,
                audit_count=audit_count,
                column_count=column_count,
                macro_call_interval=macro_call_interval,
            ),
        }
        sql: str = builders[index == _SEMANTIC_SET_OPERATION_MODEL_INDEX]()
        (model_dir / f"model_{index:05d}.sql").write_text(sql, encoding="utf-8")


def _semantic_model_column_count(*, index: int, model_count: int) -> int:
    quantile: float = (index + 1) / model_count
    upper_quantiles: tuple[float, ...] = tuple(item[0] for item in _SEMANTIC_COLUMN_COUNT_PROFILE)
    upper_index: int = bisect_left(upper_quantiles, quantile)
    lower_quantile, lower_count = _SEMANTIC_COLUMN_COUNT_PROFILE[upper_index - 1]
    upper_quantile, upper_count = _SEMANTIC_COLUMN_COUNT_PROFILE[upper_index]
    position: float = (quantile - lower_quantile) / (upper_quantile - lower_quantile)
    profile_count: int = max(3, round(lower_count + position * (upper_count - lower_count)))
    return {
        False: profile_count,
        True: 270,
    }[index == _SEMANTIC_SET_OPERATION_MODEL_INDEX]


def _semantic_model_header(
    *, index: int, model_count: int, audit_count: int, column_count: int
) -> str:
    base_audit_count, extra_audit_count = divmod(audit_count, model_count)
    model_audit_count: int = base_audit_count + int(index < extra_audit_count)
    base_columns: list[tuple[str, str]] = [
        ("id", "INTEGER"),
        ("amount", "DOUBLE"),
        ("status", "VARCHAR"),
    ]
    generated_columns: list[tuple[str, str]] = [
        (f"metric_{column_index:04d}", "DOUBLE")
        for column_index in range(column_count - len(base_columns))
    ]
    columns: list[tuple[str, str]] = [*base_columns, *generated_columns]
    declarations: list[str] = []
    for column_index, (name, data_type) in enumerate(columns):
        audit_sql: str = {False: "", True: ", audits [not_null]"}[column_index < model_audit_count]
        nullable_sql: str = {False: "", True: ", nullable false"}[column_index == 0]
        declarations.append(f"    {name} (type {data_type}{nullable_sql}{audit_sql})")
    return "MODEL (\n  columns (\n" + ",\n".join(declarations) + "\n  ),\n);"


def _semantic_regular_model_sql(
    *,
    index: int,
    model_count: int,
    source_count: int,
    seed_count: int,
    function_count: int,
    macro_count: int,
    audit_count: int,
    column_count: int,
    macro_call_interval: int = _MACRO_INTERVAL,
) -> str:
    header: str = _semantic_model_header(
        index=index,
        model_count=model_count,
        audit_count=audit_count,
        column_count=column_count,
    )
    source_index: int = _layered_base_source_index(index=index, source_count=source_count)
    relation_sql: str = {
        True: f'__source("source_{source_index:05d}")',
        False: f'__ref("model_{index - 1:05d}")',
    }[_layered_is_base_model(index=index)]
    metric_expressions: str = "".join(
        f",\n  CAST(COALESCE(CASE WHEN id % {column_index % 11 + 2} = 0 "
        f"THEN amount + {column_index} WHEN status = 'priority' "
        f"THEN amount * {column_index % 7 + 1} ELSE amount - {column_index} END, 0) AS DOUBLE) "
        f"AS metric_{column_index:04d}"
        for column_index in range(column_count - 3)
    )
    seed_index: int = index % seed_count
    seed_join_sql: str = {
        True: f'\nLEFT JOIN __seed("seed_{seed_index:05d}") AS seed ON seed.id = input.id',
        False: "",
    }[index >= _SEED_REFERENCE_START_INDEX and index % _SEED_INTERVAL == 0]
    function_index: int = index % function_count
    amount_expression: str = {
        True: f'__udf("fn_{function_index:05d}")(amount)',
        False: "amount + CAST(@@benchmark_revision AS INTEGER)",
    }[index % _FUNCTION_INTERVAL == 0]
    macro_index: int = (index // macro_call_interval) % macro_count
    id_expression: str = {
        True: f'@macro_{macro_index:05d}("id")',
        False: "id",
    }[index % macro_call_interval == 0]
    direct_sql: str = f"""SELECT
  CAST({id_expression} AS INTEGER) AS id,
  CAST({amount_expression} AS DOUBLE) AS amount,
  CAST(CASE WHEN id % 2 = 0 THEN 'even' ELSE 'odd' END AS VARCHAR) AS status{metric_expressions}
FROM {relation_sql} AS input{seed_join_sql}
"""
    with_sql: str = f"WITH transformed AS (\n{direct_sql.rstrip()}\n)\nSELECT * FROM transformed\n"
    nested_sql: str = f"SELECT * FROM (\n{direct_sql.rstrip()}\n) AS nested_query\n"
    query_sql: str = {
        (True, True): with_sql,
        (True, False): with_sql,
        (False, True): nested_sql,
        (False, False): direct_sql,
    }[
        (
            index % _TOP_LEVEL_WITH_INTERVAL == 0,
            index % _NESTED_QUERY_INTERVAL == 0,
        )
    ]
    return f"{header}\n\n{query_sql}"


def _semantic_set_operation_model_sql(
    *,
    index: int,
    source_count: int,
    column_count: int,
    model_count: int,
    audit_count: int,
) -> str:
    header: str = _semantic_model_header(
        index=index,
        model_count=model_count,
        audit_count=audit_count,
        column_count=column_count,
    )
    source_index: int = _layered_base_source_index(index=index, source_count=source_count)
    branches: str = "\nUNION ALL\n".join(
        f"SELECT {branch % 5 + 1} AS bucket, {branch * 10} AS offset_seconds, "
        f"CAST({branch % 13} AS DOUBLE) AS adjustment"
        for branch in range(_SEMANTIC_SET_OPERATION_BRANCH_COUNT)
    )
    metrics: str = "".join(
        f",\n  CAST(MAX(CASE WHEN bucket = {metric % 5 + 1} "
        f"AND offset_seconds = {metric * 10} THEN amount + adjustment END) AS DOUBLE) "
        f"AS metric_{metric:04d}"
        for metric in range(column_count - 3)
    )
    return f"""{header}

WITH offset_grid AS (
{branches}
), measurements AS (
  SELECT source.id, source.amount, source.status, grid.bucket, grid.offset_seconds, grid.adjustment
  FROM __source("source_{source_index:05d}") AS source
  CROSS JOIN offset_grid AS grid
)
SELECT
  CAST(MAX(id) AS INTEGER) AS id,
  CAST(MAX(amount) AS DOUBLE) AS amount,
  CAST(MAX(status) AS VARCHAR) AS status{metrics}
FROM measurements
"""


def _layered_write_tests(
    *,
    project_dir: Path,
    model_count: int,
    test_count: int,
    source_count: int,
    seed_count: int,
    semantic_fixture_scale: bool = False,
) -> None:
    tests_dir: Path = project_dir / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    tests_per_file: int = 4
    cases_per_target: int = 5
    repeated_target_count: int = (test_count + cases_per_target - 1) // cases_per_target
    for file_index in range((test_count + tests_per_file - 1) // tests_per_file):
        first_test_index: int = file_index * tests_per_file
        blocks: str = "\n".join(
            _layered_test_block(
                test_index=test_index,
                model_count=model_count,
                source_count=source_count,
                repeated_target_count=repeated_target_count,
                seed_count=seed_count,
                semantic_fixture_scale=semantic_fixture_scale,
            )
            for test_index in range(
                first_test_index,
                min(test_count, first_test_index + tests_per_file),
            )
        )
        (tests_dir / f"test_group_{file_index:05d}.sql").write_text(blocks, encoding="utf-8")


def _layered_test_block(
    *,
    test_index: int,
    model_count: int,
    source_count: int,
    repeated_target_count: int,
    seed_count: int,
    semantic_fixture_scale: bool = False,
) -> str:
    group_count: int = (model_count - _SPINE_DEPTH) // _TEST_CHAIN_DEPTH
    representative_group_count: int = {
        True: group_count // 3,
        False: (group_count * 2) // 3,
    }[semantic_fixture_scale]
    group_index: int = ((test_index // 5) * representative_group_count) // repeated_target_count
    base_index: int = _SPINE_DEPTH + group_index * _TEST_CHAIN_DEPTH
    target_index: int = base_index + _TEST_CHAIN_DEPTH - 1
    source_index: int = _layered_base_source_index(index=base_index, source_count=source_count)
    fixture_row_count: int = {
        True: 5 + (test_index % 5) * 5,
        False: 40 + (test_index % 5) * 40,
    }[semantic_fixture_scale]
    first_seed_index: int = max(
        _SEED_REFERENCE_START_INDEX, base_index + int(not semantic_fixture_scale)
    )
    first_seed_index = ((first_seed_index + _SEED_INTERVAL - 1) // _SEED_INTERVAL) * _SEED_INTERVAL
    seed_indexes: set[int] = {
        index % seed_count for index in range(first_seed_index, target_index + 1, _SEED_INTERVAL)
    }
    seed_fixtures: str = "".join(
        f"__seed__seed_{index:05d} AS (SELECT 1 AS id),\n" for index in sorted(seed_indexes)
    )
    return _layered_test_sql(
        test_index=test_index,
        source_index=source_index,
        target_index=target_index,
        fixture_row_count=fixture_row_count,
        include_assertion=test_index % 7 == 0,
        seed_fixtures=seed_fixtures,
    )


def _layered_test_sql(
    *,
    test_index: int,
    source_index: int,
    target_index: int,
    fixture_row_count: int,
    include_assertion: bool,
    seed_fixtures: str,
) -> str:
    fixture_rows: str = " UNION ALL\n".join(
        f"  SELECT {row} AS id, CAST({row} AS DOUBLE) AS amount, 'source' AS status"
        for row in range(fixture_row_count)
    )
    assertion_sql: str = f""",
__assert__non_negative_{target_index:05d} AS (
  SELECT * FROM __ref("model_{target_index:05d}") WHERE amount < 0
)"""
    assertion: str = {True: assertion_sql, False: ""}[include_assertion]
    return f"""TEST (name "layered_production_case_{test_index:05d}");

WITH
{seed_fixtures}__source__source_{source_index:05d} AS (
{fixture_rows}
),
__expected__model_{target_index:05d} AS (
  SELECT 1 AS id, CAST(1 AS DOUBLE) AS amount, 'odd' AS status
){assertion}
SELECT 1
"""


def _layered_base_source_index(*, index: int, source_count: int) -> int:
    base_ordinal: int = {
        True: 0,
        False: 1 + (index - _SPINE_DEPTH) // _TEST_CHAIN_DEPTH,
    }[index == 0]
    return base_ordinal % source_count


def _layered_model_sql_size_target(*, index: int, model_count: int) -> int:
    quantile: float = (index + 1) / model_count
    upper_quantiles: tuple[float, ...] = tuple(item[0] for item in _SQL_SIZE_PROFILE)
    upper_index: int = bisect_left(upper_quantiles, quantile)
    lower_quantile, lower_size = _SQL_SIZE_PROFILE[upper_index - 1]
    upper_quantile, upper_size = _SQL_SIZE_PROFILE[upper_index]
    position: float = (quantile - lower_quantile) / (upper_quantile - lower_quantile)
    return round(lower_size + position * (upper_size - lower_size))


def _layered_generated_mapping_expression() -> str:
    clauses: str = "".join(f"WHEN id = {value:05d} THEN {value % 13:02d} " for value in range(45))
    return f"CASE {clauses} ELSE 0 END"


def _layered_pad_model_sql(*, sql: str, target_bytes: int, index: int) -> str:
    missing_bytes: int = max(0, target_bytes - len(sql.encode()))
    line_template: str = "-- generated field 00000 maps source_metric to output_metric_00000\n"
    line_count: int = (missing_bytes + len(line_template) - 1) // len(line_template)
    comments: str = "".join(
        f"-- generated field {line:05d} maps source_metric to output_metric_{index:05d}\n"
        for line in range(line_count)
    )
    return f"{sql.rstrip()}\n{comments}"


def build_rule_gated_test_project_files(*, filler_model_count: int) -> dict[str, str]:
    """Build a project with one rule error and one SQL test that lacks a source mock."""

    files: dict[str, str] = {
        "sqlbuild_project.toml": (
            'name = "rule_gated_orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRMODEL102"]\n'
        ),
        "sources/raw.yml": (
            "sources:\n"
            "  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
            "  - name: raw_refunds\n    schema: main\n    table: raw_refunds\n"
        ),
        "models/orders.sql": (
            "MODEL (materialized view);\n\n"
            'SELECT o.order_id, r.refund_id FROM __source("raw_orders") AS o\n'
            'LEFT JOIN __source("raw_refunds") AS r ON r.order_id = o.order_id\n'
        ),
        "models/bad_star.sql": (
            'MODEL (materialized view);\n\nSELECT * FROM __source("raw_orders")\n'
        ),
        "tests/unit/orders_case.sql": (
            'TEST (name "orders_case");\n'
            "WITH\n"
            "__source__raw_orders AS (SELECT 1 AS order_id),\n"
            "__expected__orders AS (SELECT 1 AS order_id)\n"
            "SELECT 1\n"
        ),
    }
    for index in range(filler_model_count):
        files[f"models/filler/filler_{index:03d}.sql"] = (
            f"MODEL (materialized view);\n\nSELECT {index} AS filler_id\n"
        )
    return files


def build_empty_input_test_project_files(
    *, select: tuple[str, ...], allowed_tests_toml: str
) -> dict[str, str]:
    """Build an orders project mixing empty-input-only filler with real SQL tests."""

    selected: str = ", ".join(f'"{code}"' for code in select)
    empty_orders: str = (
        "__source__raw_orders AS (\n"
        "  SELECT CAST(NULL AS INTEGER) AS order_id, CAST(NULL AS INTEGER) AS amount\n"
        "  WHERE FALSE\n"
        ")"
    )
    return {
        "sqlbuild_project.toml": (
            'name = "empty_input_orders"\nadapter = "duckdb"\n\n'
            f"[rules]\nselect = [{selected}]\n\n"
            "[rules.thresholds]\nmin_tests_per_model = 1\n\n"
            f"[rules.rule_options.SQBRTEST203]\nallowed_tests = {allowed_tests_toml}\n"
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (materialized view);\n\n"
            "SELECT order_id, amount * 2 AS doubled_amount\n"
            'FROM __source("raw_orders")\nWHERE amount > 0\n'
        ),
        "models/large_orders.sql": (
            "MODEL (materialized view);\n\n"
            'SELECT order_id FROM __source("raw_orders") WHERE amount > 100\n'
        ),
        "models/customers.sql": (
            "MODEL (materialized view);\n\n"
            'SELECT order_id AS customer_id FROM __source("raw_orders") WHERE amount > 10\n'
        ),
        "models/order_summary.sql": (
            "MODEL (materialized view);\n\n"
            "SELECT COUNT(*) AS order_count, COALESCE(SUM(amount), 0) AS total_amount\n"
            'FROM __source("raw_orders")\n'
        ),
        "tests/unit/test_orders__empty_inputs_produce_no_rows.sql": (
            'TEST (name "orders__empty_inputs_produce_no_rows");\n\n'
            f"WITH {empty_orders}, __assert__empty_inputs_produce_no_rows AS (\n"
            '  SELECT 1 AS unexpected_row FROM __ref("orders")\n'
            ")\nSELECT 1\n"
        ),
        "tests/unit/test_large_orders__empty_inputs_produce_no_rows.sql": (
            'TEST (name "large_orders__empty_inputs_produce_no_rows");\n\n'
            f"WITH {empty_orders}, __expected__large_orders AS (\n"
            "  SELECT * FROM __EMPTY_FIXTURE()\n"
            ")\nSELECT 1\n"
        ),
        "tests/unit/test_large_orders__keeps_orders_over_threshold.sql": (
            'TEST (name "large_orders__keeps_orders_over_threshold");\n\n'
            "WITH __source__raw_orders AS (\n"
            "  SELECT 1 AS order_id, 150 AS amount UNION ALL SELECT 2 AS order_id, 20 AS amount\n"
            "), __expected__large_orders AS (\n"
            "  SELECT 1 AS order_id\n"
            ")\nSELECT 1\n"
        ),
        "tests/unit/test_customers__reviewed_empty_input.sql": (
            'TEST (name "customers__reviewed_empty_input");\n\n'
            f"WITH {empty_orders}, __assert__no_customers AS (\n"
            '  SELECT customer_id FROM __ref("customers")\n'
            ")\nSELECT 1\n"
        ),
        "tests/unit/test_order_summary__empty_inputs_return_zero_row.sql": (
            'TEST (name "order_summary__empty_inputs_return_zero_row");\n\n'
            f"WITH {empty_orders}, __expected__order_summary AS (\n"
            "  SELECT 0 AS order_count, 0 AS total_amount\n"
            ")\nSELECT 1\n"
        ),
    }
