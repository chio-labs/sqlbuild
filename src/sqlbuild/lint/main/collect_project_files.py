"""Stable internal entry for SQL analysis project-file collection."""

from pathlib import Path

from sqlbuild.lint._helpers.project_files import collect_project_files as _collect_project_files


def collect_project_files(
    *, project_dir: Path, selected_paths: frozenset[Path] | None
) -> dict[Path, str]:
    """Collect supported SQL-analysis inputs for a project or selected path set."""

    return _collect_project_files(project_dir=project_dir, selected_paths=selected_paths)
