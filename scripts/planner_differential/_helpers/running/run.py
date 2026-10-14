"""Run the corpus in parallel and compare or record each project."""

from __future__ import annotations

import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from scripts.planner_differential._helpers.baseline.baseline import (
    compare_documents,
    read_document,
    write_document,
)
from scripts.planner_differential._helpers.running.project_run import project_slug, run_project
from scripts.planner_differential._helpers.running.report import format_result
from scripts.planner_differential.constants import ACTUAL_SUFFIX, MODE_RECORD
from scripts.planner_differential.models import PlannerProject, ProjectResult, RunOptions


def run_corpus(*, projects: list[PlannerProject], options: RunOptions) -> list[ProjectResult]:
    """Run every project, printing each verdict as it completes."""

    print(
        f"Planner differential {options.mode}: {len(projects)} projects x "
        f"{len(options.steps)} steps ({options.jobs} jobs), baseline {options.baseline_dir}",
        file=sys.stderr,
    )
    results: list[ProjectResult] = []
    with ThreadPoolExecutor(max_workers=options.jobs) as pool:
        for result in pool.map(
            lambda project: _project_result(project=project, options=options), projects
        ):
            results.append(result)
            print(format_result(result))
            sys.stdout.flush()
    return results


def _project_result(*, project: PlannerProject, options: RunOptions) -> ProjectResult:
    started: float = time.monotonic()
    slug: str = project_slug(project.name)
    try:
        document: dict[str, object] = run_project(project=project, options=options)
    except Exception:  # noqa: BLE001 - one project's harness failure must not hide the others
        return ProjectResult(
            project=project.name,
            seconds=time.monotonic() - started,
            differences=(),
            error=traceback.format_exc(),
        )
    if options.mode == MODE_RECORD:
        _ = write_document(directory=options.baseline_dir, slug=slug, document=document)
        return ProjectResult(
            project=project.name, seconds=time.monotonic() - started, differences=()
        )
    _ = write_document(
        directory=options.baseline_dir.with_name(options.baseline_dir.name + ACTUAL_SUFFIX),
        slug=slug,
        document=document,
    )
    expected: dict[str, object] | None = read_document(directory=options.baseline_dir, slug=slug)
    if expected is None:
        return ProjectResult(
            project=project.name,
            seconds=time.monotonic() - started,
            differences=(),
            error=f"no baseline for {project.name}; run with `record` first",
        )
    return ProjectResult(
        project=project.name,
        seconds=time.monotonic() - started,
        differences=compare_documents(expected=expected, actual=document),
    )
