"""Compile command DAG artifact helpers."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.compile.constants import EMPTY_DAG_PATH


def resolve_compile_dag_path(*, project_dir: Path, dag_path: str) -> Path:
    """Resolve the optional compile DAG artifact path."""

    if dag_path == EMPTY_DAG_PATH:
        return project_dir / "target" / "sqlbuild_dag.json"
    path: Path = Path(dag_path)
    if path.is_absolute():
        return path
    return project_dir / path
