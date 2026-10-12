"""Run one corpus project and check it against its expectation and golden."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from scripts.compiler_differential._helpers.comparing.comparison import diagnostic_codes
from scripts.compiler_differential._helpers.coverage.analysis import project_analysis_kinds
from scripts.compiler_differential._helpers.coverage.discovery import project_discovery_kinds
from scripts.compiler_differential._helpers.coverage.render import project_render_kinds
from scripts.compiler_differential._helpers.goldens.goldens import (
    golden_differences,
    golden_path_masks,
)
from scripts.compiler_differential._helpers.running.evidence import keep_failure_evidence
from scripts.compiler_differential._helpers.running.execution import run_project
from scripts.compiler_differential.constants import (
    ERROR_SEVERITY,
    WARNING_SEVERITY,
)
from scripts.compiler_differential.models import (
    CommandOutcome,
    CorpusProject,
    Difference,
    DifferentialOptions,
    ProjectComparison,
    ProjectRun,
)

_SOURCE_DIRECTORY: str = "source"
_CORPUS_ARTIFACT: str = "corpus expectation"
_EXPECTATION_LABELS: tuple[str, str] = ("expected", "actual")


def compare_project(*, project: CorpusProject, options: DifferentialOptions) -> ProjectComparison:
    """Check one project against its expectation and golden; any timeout fails."""

    started: float = time.monotonic()
    case_dir: Path = options.work_dir / project.name.replace("/", "__")
    shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True)
    source_dir: Path = _materialized_source(project=project, case_dir=case_dir)
    run: ProjectRun = run_project(
        project=project, source_dir=source_dir, case_dir=case_dir, options=options
    )
    counted: bool = project.seed_coverage and options.stage_captures
    differences: list[Difference] = [
        *_timeout_differences(project=project, run=run),
        *_corpus_differences(project=project, run=run),
        *(
            golden_differences(
                project=project,
                run=run,
                golden_dir=options.golden_dir,
                mode=options.golden_mode,
                masked_paths=golden_path_masks(case_dir=case_dir, work_dir=options.work_dir),
            )
            if options.golden_mode is not None and options.golden_dir is not None
            else ()
        ),
    ]
    if differences and options.evidence_dir is not None:
        _ = keep_failure_evidence(
            case_dir=case_dir,
            project_subdirectory=project.project_subdirectory,
            run=run,
            evidence_dir=options.evidence_dir,
        )
    return ProjectComparison(
        project=project.name,
        differences=tuple(differences),
        seconds=time.monotonic() - started,
        discovered_kinds=(
            project_discovery_kinds(captures=run.captures, source_dir=source_dir)
            if counted
            else frozenset()
        ),
        rendered_kinds=project_render_kinds(run.captures) if counted else frozenset(),
        analysed_kinds=project_analysis_kinds(run.captures) if counted else frozenset(),
    )


def _materialized_source(*, project: CorpusProject, case_dir: Path) -> Path:
    if project.source_dir is not None:
        return project.source_dir
    source_dir: Path = case_dir / _SOURCE_DIRECTORY
    if project.writer is not None:
        project.writer(source_dir)
    return source_dir


def _corpus_differences(*, project: CorpusProject, run: ProjectRun) -> list[Difference]:
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
        if (outcome.exit_code != 0) != (outcome.label in project.expected.refused_commands)
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


def _timeout_differences(*, project: CorpusProject, run: ProjectRun) -> list[Difference]:
    return [
        _expectation_difference(
            project=project,
            location=f"`{outcome.label}`",
            expected="completes within the command timeout",
            actual="timed out",
        )
        for outcome in run.outcomes
        if outcome.timed_out
    ]


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
