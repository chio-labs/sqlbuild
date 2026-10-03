"""Generate benchmark projects and time alternating base and head compiles."""

from __future__ import annotations

import json
import os
import resource
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from scripts.cold_compile_performance._helpers.dense_project import write_dense_compile_project
from scripts.compile_performance_ratio.constants import (
    BASE_GENERATOR_ENTRY,
    BASE_LABEL,
    COMPILE_ENTRY,
    DENSE_KIND,
    ERROR_TAIL_CHARACTERS,
    EXCLUDED_ENVIRONMENT_KEYS,
    EXCLUDED_ENVIRONMENT_PREFIX,
    FRESH_AUDIT_SHARE,
    FRESH_FUNCTION_SHARE,
    FRESH_MACRO_SHARE,
    FRESH_SEED_SHARE,
    FRESH_SOURCE_SHARE,
    FRESH_TEST_SHARE,
    HEAD_LABEL,
    PYTHONPATH_KEY,
    REPORTED_PHASES,
)
from scripts.compile_performance_ratio.exceptions import CompileComparisonError
from scripts.compile_performance_ratio.models import CompileComparison, CompileRun
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    write_semantic_compile_project,
)


def write_benchmark_project(*, kind: str, project_dir: Path, models: int) -> None:
    """Write the dense or fresh benchmark project used by both builds."""

    if kind == DENSE_KIND:
        write_dense_compile_project(project_dir=project_dir, model_count=models)
        return
    write_semantic_compile_project(
        project_dir=project_dir,
        model_count=models,
        source_count=max(1, round(models * FRESH_SOURCE_SHARE)),
        seed_count=max(1, round(models * FRESH_SEED_SHARE)),
        function_count=max(1, round(models * FRESH_FUNCTION_SHARE)),
        macro_count=max(1, round(models * FRESH_MACRO_SHARE)),
        test_count=max(1, round(models * FRESH_TEST_SHARE)),
        audit_count=max(1, round(models * FRESH_AUDIT_SHARE)),
    )


def run_checkout_generator(
    *,
    checkout: Path,
    python: Path,
    entry: str,
    arguments: tuple[str, ...],
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run generator code from another checkout's source tree with this `python`."""

    return subprocess.run(
        [str(python), "-c", entry, *arguments],
        cwd=checkout,
        capture_output=True,
        text=True,
        env={**environment, PYTHONPATH_KEY: str(checkout)},
        check=False,
    )


def write_base_benchmark_project(
    *, base_root: Path, python: Path, kind: str, project_dir: Path, models: int
) -> None:
    """Write the base project with the base checkout's own generator, run by `python`."""

    completed: subprocess.CompletedProcess[str] = run_checkout_generator(
        checkout=base_root,
        python=python,
        entry=BASE_GENERATOR_ENTRY,
        arguments=(kind, str(project_dir), str(models)),
        environment=_compile_environment(),
    )
    if completed.returncode != 0:
        raise CompileComparisonError(
            f"base project generation in {base_root} failed with exit {completed.returncode}: "
            f"{completed.stderr[-ERROR_TAIL_CHARACTERS:]}"
        )


def compare_builds(
    *,
    kind: str,
    models: int,
    base_project_dir: Path,
    head_project_dir: Path,
    base_python: Path,
    head_python: Path,
    runs: int,
) -> CompileComparison:
    """Alternate base and head cold compiles after one untimed warm-up compile per build."""

    builds: tuple[tuple[str, Path, Path], ...] = (
        (BASE_LABEL, base_python, base_project_dir),
        (HEAD_LABEL, head_python, head_project_dir),
    )
    for label, python, project_dir in builds:
        _compile_once(label=label, python=python, project_dir=project_dir)
    results: dict[str, list[CompileRun]] = {BASE_LABEL: [], HEAD_LABEL: []}
    for _ in range(runs):
        for label, python, project_dir in builds:
            results[label].append(
                _compile_once(label=label, python=python, project_dir=project_dir)
            )
    base: list[CompileRun] = results[BASE_LABEL]
    head: list[CompileRun] = results[HEAD_LABEL]
    return CompileComparison(
        kind=kind,
        models=models,
        base_wall_seconds=statistics.median(run.wall_seconds for run in base),
        head_wall_seconds=statistics.median(run.wall_seconds for run in head),
        base_cpu_seconds=statistics.median(run.cpu_seconds for run in base),
        head_cpu_seconds=statistics.median(run.cpu_seconds for run in head),
        base_timings_ms=_median_phases(runs=base),
        head_timings_ms=_median_phases(runs=head),
    )


def _compile_once(*, label: str, python: Path, project_dir: Path) -> CompileRun:
    shutil.rmtree(project_dir / "target", ignore_errors=True)
    environment: dict[str, str] = _compile_environment()
    before: resource.struct_rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
    started: float = time.perf_counter()
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(python),
            "-c",
            COMPILE_ENTRY,
            "--project-dir",
            str(project_dir),
            "--no-color",
            "compile",
            "--json",
            "--no-cache",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    wall_seconds: float = time.perf_counter() - started
    after: resource.struct_rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
    if completed.returncode != 0:
        raise CompileComparisonError(
            f"{label} compile failed with exit {completed.returncode}: "
            f"{completed.stderr[-ERROR_TAIL_CHARACTERS:]}"
        )
    payload: dict[str, object] = json.loads(completed.stdout)
    timings: object = payload.get("compile_timings", {})
    return CompileRun(
        label=label,
        wall_seconds=wall_seconds,
        cpu_seconds=(after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime),
        timings_ms={
            name: int(value)
            for name, value in (timings.items() if isinstance(timings, dict) else ())
            if name in REPORTED_PHASES and isinstance(value, (int, float))
        },
    )


def _compile_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key not in EXCLUDED_ENVIRONMENT_KEYS and not key.startswith(EXCLUDED_ENVIRONMENT_PREFIX)
    }


def _median_phases(*, runs: list[CompileRun]) -> dict[str, float]:
    medians: dict[str, float] = {}
    for phase in REPORTED_PHASES:
        values: list[int] = [run.timings_ms.get(phase, 0) for run in runs]
        medians[phase] = statistics.median(values)
    return medians
