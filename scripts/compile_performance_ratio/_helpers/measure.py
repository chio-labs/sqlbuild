"""Generate a benchmark project once and time alternating base and head compiles."""

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
    BASE_LABEL,
    COMPILE_ENTRY,
    DENSE_KIND,
    FRESH_AUDIT_SHARE,
    FRESH_FUNCTION_SHARE,
    FRESH_MACRO_SHARE,
    FRESH_SEED_SHARE,
    FRESH_SOURCE_SHARE,
    FRESH_TEST_SHARE,
    HEAD_LABEL,
    REPORTED_PHASES,
)
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


def compare_builds(
    *,
    kind: str,
    models: int,
    project_dir: Path,
    base_python: Path,
    head_python: Path,
    runs: int,
) -> CompileComparison:
    """Alternate base and head cold compiles of one project on the same machine.

    One untimed compile per build first warms imports and the file cache, so neither
    build pays the process's first-run cost inside the measurement.
    """

    builds: tuple[tuple[str, Path], ...] = ((BASE_LABEL, base_python), (HEAD_LABEL, head_python))
    for label, python in builds:
        _compile_once(label=label, python=python, project_dir=project_dir)
    results: dict[str, list[CompileRun]] = {BASE_LABEL: [], HEAD_LABEL: []}
    for _ in range(runs):
        for label, python in builds:
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
    environment: dict[str, str] = {
        key: value
        for key, value in os.environ.items()
        if key != "VIRTUAL_ENV" and not key.startswith("DBT_")
    }
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
        raise RuntimeError(
            f"{label} compile failed with exit {completed.returncode}: {completed.stderr[-2000:]}"
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


def _median_phases(*, runs: list[CompileRun]) -> dict[str, float]:
    return {
        phase: statistics.median(run.timings_ms.get(phase, 0) for run in runs)
        for phase in REPORTED_PHASES
    }
