"""Assemble the projects the differential harness compares."""

from __future__ import annotations

import itertools
import tomllib
from pathlib import Path

from scripts.compiler_differential._helpers.corpus.failure_cases import all_failure_cases
from scripts.compiler_differential._helpers.refactor_corpus.refactor_cases import refactor_cases
from scripts.compiler_differential.classes.dense_project import DenseProject
from scripts.compiler_differential.classes.project_builder import ProjectBuilder
from scripts.compiler_differential.constants import (
    ANALYSIS_DIALECT_VARIANTS,
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
    GENERATOR_DIALECT_BLOCKS,
    PLAN,
    PROJECT_CONFIG_FILE,
    STORE_WARM_COMPILE,
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
        entries.extend(
            _dialect_seed_project(seed=seed, dialect=dialect)
            for seed, dialect in itertools.product(seeds[:1], ANALYSIS_DIALECT_VARIANTS)
        )
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
        entries.extend(refactor_cases())
    if CORPUS_DENSE in corpora:
        entries.extend(
            CorpusProject(
                name=f"dense/{dense_models}{'-custom-rules' if custom_rules else ''}",
                commands=(COLD_COMPILE, WARM_COMPILE, STORE_WARM_COMPILE),
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
        commands=(COLD_COMPILE, WARM_COMPILE, STORE_WARM_COMPILE, *_plan_commands(project_dir)),
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
        commands=(COLD_COMPILE, STORE_WARM_COMPILE, PLAN, *generated.extra_commands),
        expected=ExpectedOutcome(
            error_code=generated.expected_error_code,
            succeeding_commands=generated.succeeding_commands,
        ),
        writer=generated.write,
        seed_coverage=True,
    )


def _dialect_seed_project(*, seed: int, dialect: str) -> CorpusProject:
    """Compile a seed's analysis blocks under another adapter's dialect; plan needs a warehouse."""

    generated: GeneratedProject = ProjectBuilder(
        seed, blocks=GENERATOR_DIALECT_BLOCKS, dialect=dialect
    ).build()
    return CorpusProject(
        name=f"seed/{seed}-{dialect}",
        commands=(COLD_COMPILE,),
        expected=EXPECT_SUCCESS,
        writer=generated.write,
        seed_coverage=True,
    )
