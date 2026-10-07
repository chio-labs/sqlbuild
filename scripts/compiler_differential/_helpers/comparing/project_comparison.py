"""Run one corpus project under both engines and compare what they produced."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.comparison import (
    compare_engine_runs,
    diagnostic_codes,
)
from scripts.compiler_differential._helpers.coverage.discovery import project_discovery_kinds
from scripts.compiler_differential._helpers.running.execution import run_engine
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
        options=options,
    )
    right: EngineRun = run_engine(
        project=project,
        source_dir=source_dir,
        case_dir=case_dir,
        engine=right_engine,
        options=options,
    )
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
            if project.discovery_coverage and options.stage_captures
            else frozenset()
        ),
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
    errors: tuple[str, ...] = diagnostic_codes(outcome=first, errors_only=True)
    expected_code: str | None = project.expected.error_code
    if expected_code is not None:
        codes: tuple[str, ...] = diagnostic_codes(outcome=first, errors_only=False)
        met: bool = first.exit_code != 0 and bool(errors) and expected_code in codes
        failed: list[Difference] = (
            []
            if met
            else [
                _expectation_difference(
                    project=project,
                    location="expected failure",
                    expected=f"non-zero exit reporting {expected_code}",
                    actual=f"exit {first.exit_code}: {', '.join(codes) or '<no codes>'}",
                )
            ]
        )
        return failed + [
            _expectation_difference(
                project=project,
                location=f"`{outcome.label}` expected success",
                expected="exit 0",
                actual=f"exit {outcome.exit_code}",
            )
            for outcome in run.outcomes
            if outcome.label in project.expected.succeeding_commands and outcome.exit_code != 0
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
