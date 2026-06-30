"""Public project-local adapter discovery entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.shared.helpers.project_adapters import (
    discover_project_adapters as _discover_project_adapters,
)
from sqlbuild.adapter.strict.strict_adapter import StrictAdapter


def discover_project_adapters(
    *,
    project_dir: Path,
    reserved_names: frozenset[str] = frozenset(),
) -> dict[str, type[StrictAdapter]]:
    """Discover adapter classes from a project's adapters directory."""

    return _discover_project_adapters(
        project_dir=project_dir,
        reserved_names=reserved_names,
    )
