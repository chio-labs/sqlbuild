"""Assemble the projects the differential harness compares."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.compiler_differential._helpers.corpus.failure_cases import all_failure_cases
from scripts.compiler_differential.classes.dense_project import DenseProject
from scripts.compiler_differential.classes.project_builder import ProjectBuilder
from scripts.compiler_differential.constants import (
    COLD_COMPILE,
    CORPUS_DENSE,
    CORPUS_EXAMPLES,
    CORPUS_FAILURES,
    CORPUS_FIXTURES,
    CORPUS_SEEDS,
    DUCKDB_ADAPTER,
    EXAMPLE_ROOT,
    EXPECT_SUCCESS,
    FIXTURE_EXPECTED_OUTCOMES,
    FIXTURE_PROJECT_SUBDIRECTORIES,
    FIXTURE_ROOT,
    PLAN,
    PROJECT_CONFIG_FILE,
    WARM_COMPILE,
)
from scripts.compiler_differential.models import (
    CorpusProject,
    DifferentialCommand,
    ExpectedOutcome,
    GeneratedProject,
)


def build_corpus(
    *,
    repo_root: Path,
    corpora: tuple[str, ...],
    seeds: range,
    dense_models: int,
    projects: tuple[Path, ...],
    project_expectation: ExpectedOutcome,
) -> list[CorpusProject]:
    """Return the selected corpus entries in a stable order."""

    entries: list[CorpusProject] = [
        _authored_project(
            name=f"project/{path.name}",
            source_dir=path,
            subdirectory=None,
            expected=project_expectation,
        )
        for path in projects
    ]
    if CORPUS_FIXTURES in corpora:
        entries.extend(
            _authored_project(
                name=f"fixture/{path.name}",
                source_dir=path,
                subdirectory=FIXTURE_PROJECT_SUBDIRECTORIES.get(path.name),
                expected=FIXTURE_EXPECTED_OUTCOMES.get(path.name, EXPECT_SUCCESS),
            )
            for path in _project_directories(repo_root / FIXTURE_ROOT)
        )
    if CORPUS_EXAMPLES in corpora:
        entries.extend(
            _authored_project(
                name=f"example/{path.name}",
                source_dir=path,
                subdirectory=None,
                expected=EXPECT_SUCCESS,
            )
            for path in _project_directories(repo_root / EXAMPLE_ROOT)
        )
    if CORPUS_SEEDS in corpora:
        entries.extend(_seed_project(seed) for seed in seeds)
    if CORPUS_FAILURES in corpora:
        entries.extend(
            CorpusProject(
                name=f"failure/{case.name}",
                commands=(COLD_COMPILE,),
                expected=ExpectedOutcome(
                    error_code=case.expected_code, warning_code=case.expected_warning_code
                ),
                writer=case.write,
            )
            for case in all_failure_cases()
        )
    if CORPUS_DENSE in corpora:
        entries.extend(
            CorpusProject(
                name=f"dense/{dense_models}{'-custom-rules' if custom_rules else ''}",
                commands=(COLD_COMPILE, WARM_COMPILE),
                expected=EXPECT_SUCCESS,
                writer=DenseProject(model_count=dense_models, custom_rules=custom_rules).write,
            )
            for custom_rules in (False, True)
        )
    return entries


def _project_directories(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and ((path / PROJECT_CONFIG_FILE).is_file() or path.name in FIXTURE_PROJECT_SUBDIRECTORIES)
    )


def _authored_project(
    *, name: str, source_dir: Path, subdirectory: str | None, expected: ExpectedOutcome
) -> CorpusProject:
    project_dir: Path = source_dir if subdirectory is None else source_dir / subdirectory
    return CorpusProject(
        name=name,
        commands=(COLD_COMPILE, WARM_COMPILE, *_plan_commands(project_dir)),
        expected=expected,
        source_dir=source_dir,
        project_subdirectory=subdirectory,
    )


def _plan_commands(project_dir: Path) -> tuple[DifferentialCommand, ...]:
    config_path: Path = project_dir / PROJECT_CONFIG_FILE
    if not config_path.is_file():
        return ()
    try:
        adapter: object = tomllib.loads(config_path.read_text(encoding="utf-8")).get("adapter")
    except tomllib.TOMLDecodeError:
        return ()
    return (PLAN,) if adapter == DUCKDB_ADAPTER else ()


def _seed_project(seed: int) -> CorpusProject:
    generated: GeneratedProject = ProjectBuilder(seed).build()
    return CorpusProject(
        name=f"seed/{seed}",
        commands=(COLD_COMPILE, PLAN),
        expected=ExpectedOutcome(
            error_code=generated.expected_error_code,
            succeeding_commands=generated.succeeding_commands,
        ),
        writer=generated.write,
        seed_coverage=True,
    )
