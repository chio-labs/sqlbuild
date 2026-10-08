"""Run one corpus project under both engines and compare what they produced."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.comparison import (
    compare_engine_runs,
    diagnostic_codes,
)
from scripts.compiler_differential._helpers.coverage.analysis import project_analysis_kinds
from scripts.compiler_differential._helpers.coverage.discovery import project_discovery_kinds
from scripts.compiler_differential._helpers.coverage.render import project_render_kinds
from scripts.compiler_differential._helpers.running.execution import run_engine
from scripts.compiler_differential.constants import (
    ERROR_SEVERITY,
    LEFT_SIDE,
    RIGHT_SIDE,
    WARNING_SEVERITY,
)
from scripts.compiler_differential.models import (
    CommandOutcome,
    CorpusProject,
    Difference,
    DifferentialOptions,
    EngineRun,
    ProjectComparison,
)

_SOURCE_DIRECTORY: str = "source"
_CORPUS_ARTIFACT: str = "corpus expectation"
_EXPECTATION_LABELS: tuple[str, str] = ("expected", "actual")


def compare_project(*, project: CorpusProject, options: DifferentialOptions) -> ProjectComparison:
    """Compare both engines on one project against its expectation; any timeout fails."""

    started: float = time.monotonic()
    case_dir: Path = options.work_dir / project.name.replace("/", "__")
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True)
    source_dir: Path = _materialized_source(project=project, case_dir=case_dir)
    left_engine, right_engine = options.engines
    left: EngineRun = run_engine(
        project=project,
        source_dir=source_dir,
        case_dir=case_dir,
        engine=left_engine,
        side=LEFT_SIDE,
        options=options,
    )
    right: EngineRun = run_engine(
        project=project,
        source_dir=source_dir,
        case_dir=case_dir,
        engine=right_engine,
        side=RIGHT_SIDE,
        options=options,
    )
    counted: bool = project.seed_coverage and options.stage_captures
    differences: list[Difference] = [
        *_timeout_differences(project=project, runs=(left, right)),
        *_corpus_differences(project=project, run=left),
        *compare_engine_runs(project=project.name, left=left, right=right),
    ]
    return ProjectComparison(
        project=project.name,
        differences=tuple(differences),
        seconds=time.monotonic() - started,
        discovered_kinds=(
            project_discovery_kinds(captures=left.captures, source_dir=source_dir)
            if counted
            else frozenset()
        ),
        rendered_kinds=project_render_kinds(left.captures) if counted else frozenset(),
        analysed_kinds=project_analysis_kinds(left.captures) if counted else frozenset(),
        records=(left.records, right.records) if options.analysis_records else None,
    )


def _materialized_source(*, project: CorpusProject, case_dir: Path) -> Path:
    if project.source_dir is not None:
        return project.source_dir
    source_dir: Path = case_dir / _SOURCE_DIRECTORY
    if project.writer is not None:
        project.writer(source_dir)
    return source_dir


def _corpus_differences(*, project: CorpusProject, run: EngineRun) -> list[Difference]:
    first: CommandOutcome = run.outcomes[0]
    errors: tuple[str, ...] = diagnostic_codes(outcome=first, severity=ERROR_SEVERITY)
    if project.expected.error_code is not None:
        return [
            *_failure_differences(project=project, outcome=first, errors=errors),
            *(
                _expectation_difference(
                    project=project,
                    location=f"`{outcome.label}` expected success",
                    expected="exit 0",
                    actual=f"exit {outcome.exit_code}",
                )
                for outcome in run.outcomes
                if outcome.label in project.expected.succeeding_commands and outcome.exit_code != 0
            ),
        ]
    problems: list[str] = [
        f"`{outcome.label}` exit {outcome.exit_code}"
        for outcome in run.outcomes
        if outcome.exit_code != 0
    ]
    if errors:
        problems.append(f"compile errors {', '.join(errors)}")
    if not problems:
        return []
    return [
        _expectation_difference(
            project=project,
            location="expected success",
            expected="every command exits 0 and compile reports no errors",
            actual="; ".join(problems),
        )
    ]


def _failure_differences(
    *, project: CorpusProject, outcome: CommandOutcome, errors: tuple[str, ...]
) -> list[Difference]:
    expected_code: str | None = project.expected.error_code
    differences: list[Difference] = []
    if outcome.exit_code == 0 or not errors or errors[0] != expected_code:
        differences.append(
            _expectation_difference(
                project=project,
                location="expected failure",
                expected=f"non-zero exit whose first error is {expected_code}",
                actual=f"exit {outcome.exit_code}: errors {', '.join(errors) or '<none>'}",
            )
        )
    warning_code: str | None = project.expected.warning_code
    warnings: tuple[str, ...] = diagnostic_codes(outcome=outcome, severity=WARNING_SEVERITY)
    if warning_code is not None and warning_code not in warnings:
        differences.append(
            _expectation_difference(
                project=project,
                location="expected warning",
                expected=f"warning {warning_code}",
                actual=f"warnings {', '.join(warnings) or '<none>'}",
            )
        )
    return differences


def _timeout_differences(
    *, project: CorpusProject, runs: tuple[EngineRun, ...]
) -> list[Difference]:
    differences: list[Difference] = []
    for run in runs:
        differences.extend(
            _expectation_difference(
                project=project,
                location=f"{run.engine} `{outcome.label}`",
                expected="completes within the command timeout",
                actual="timed out",
            )
            for outcome in run.outcomes
            if outcome.timed_out
        )
    return differences


def _expectation_difference(
    *, project: CorpusProject, location: str, expected: str, actual: str
) -> Difference:
    return Difference(
        project=project.name,
        artifact=_CORPUS_ARTIFACT,
        location=location,
        left=expected,
        right=actual,
        labels=_EXPECTATION_LABELS,
    )
