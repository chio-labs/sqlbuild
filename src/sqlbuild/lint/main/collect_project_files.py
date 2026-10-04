"""Stable internal entry for SQL analysis project-file collection."""

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint._helpers.project_files import collect_project_files as _collect_project_files


def collect_project_files(
    *,
    project_dir: Path,
    selected_paths: frozenset[Path] | None,
    discovered_inputs: DiscoveredProjectInputs | None = None,
) -> dict[Path, str]:
    """Collect supported SQL-analysis inputs, sharing text discovery already holds."""

    return _collect_project_files(
        project_dir=project_dir,
        selected_paths=selected_paths,
        discovered_inputs=discovered_inputs,
    )
