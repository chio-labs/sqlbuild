"""Select the fixture, example and generated projects the planner differential runs."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.compiler_differential.classes.project_builder import ProjectBuilder
from scripts.compiler_differential.models import GeneratedProject
from scripts.planner_differential.constants import (
    DUCKDB_ADAPTER,
    EXAMPLE_ROOT,
    FIXTURE_ROOT,
    PROJECT_CONFIG_FILE,
)
from scripts.planner_differential.models import PlannerProject

_SEED_SEARCH_FACTOR: int = 10
_FIXTURE_KIND: str = "fixture"
_EXAMPLE_KIND: str = "example"


def build_corpus(*, repo_root: Path, seed_start: int, seeds: int) -> list[PlannerProject]:
    """Return DuckDB fixtures and examples, then the first `seeds` valid built-in DuckDB seeds."""

    projects: list[PlannerProject] = []
    for kind, root in ((_FIXTURE_KIND, FIXTURE_ROOT), (_EXAMPLE_KIND, EXAMPLE_ROOT)):
        projects.extend(
            PlannerProject(name=f"{kind}/{path.name}", source_dir=path)
            for path in _duckdb_projects(repo_root / root)
        )
    found: int = 0
    for seed in range(seed_start, seed_start + seeds * _SEED_SEARCH_FACTOR):
        if found == seeds:
            break
        generated: GeneratedProject = ProjectBuilder(seed).build()
        if generated.expected_error_code is not None or not _duckdb_config(
            generated.files.get(PROJECT_CONFIG_FILE, "")
        ):
            continue
        projects.append(PlannerProject(name=f"seed/{seed}", writer=generated.write))
        found += 1
    return projects


def filter_corpus(
    *, projects: list[PlannerProject], names: tuple[str, ...], limit: int | None
) -> list[PlannerProject]:
    """Keep projects whose name contains any filter, then the first `limit` of them."""

    kept: list[PlannerProject] = [
        project for project in projects if not names or _matches(name=project.name, filters=names)
    ]
    return kept if limit is None else kept[:limit]


def _matches(*, name: str, filters: tuple[str, ...]) -> bool:
    return any(item in name for item in filters)


def _duckdb_projects(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and (path / PROJECT_CONFIG_FILE).is_file()
        and _duckdb_config((path / PROJECT_CONFIG_FILE).read_text(encoding="utf-8"))
    )


def _duckdb_config(text: str) -> bool:
    try:
        return tomllib.loads(text).get("adapter") == DUCKDB_ADAPTER
    except tomllib.TOMLDecodeError:
        return False
