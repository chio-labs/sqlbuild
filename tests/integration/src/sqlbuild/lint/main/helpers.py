"""Compile small DuckDB projects for Rule-fix verification tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.pipeline.main.project import compile_project

_PROJECT_TOML: str = 'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'


def compile_models(*, project_dir: Path, models: tuple[tuple[str, str], ...]) -> CompiledProject:
    """Write and compile the models."""

    (project_dir / "sqlbuild_project.toml").write_text(_PROJECT_TOML, encoding="utf-8")
    (project_dir / "models").mkdir(exist_ok=True)
    for name, sql in models:
        (project_dir / "models" / name).write_text(sql, encoding="utf-8")
    return compile_project(
        discovered_inputs=discover_project_inputs(project_dir=project_dir),
        adapter=DuckDbAdapter(),
    )


def without_lineage(project: CompiledProject) -> CompiledProject:
    """The same compilation with column lineage unavailable for every model."""

    return replace(
        project,
        models=tuple(replace(model, fast_lineage_columns=None) for model in project.models),
    )
