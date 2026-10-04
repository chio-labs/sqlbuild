"""Collect authored SQL files for lint and format runs."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.lint.constants import LINT_DIRECTORY_NAMES


def collect_project_files(
    *,
    project_dir: Path,
    selected_paths: frozenset[Path] | None = None,
    source_files: dict[Path, str] | None = None,
    discovered_inputs: DiscoveredProjectInputs | None = None,
) -> dict[Path, str]:
    """Return authored SQL files keyed by path, sharing identical text discovery already holds."""

    if source_files is not None:
        return {
            file_path: contents
            for file_path, contents in source_files.items()
            if selected_paths is None or file_path.resolve() in selected_paths
        }
    discovered: dict[Path, str] = (
        {} if discovered_inputs is None else discovered_sql_contents(discovered_inputs)
    )
    files: dict[Path, str] = {}
    directory_name: str
    for directory_name in LINT_DIRECTORY_NAMES:
        root: Path = project_dir / directory_name
        if not root.is_dir():
            continue
        file_path: Path
        for file_path in sorted(root.rglob("*.sql")):
            if selected_paths is not None and file_path.resolve() not in selected_paths:
                continue
            with file_path.open("r", encoding="utf-8", newline="") as handle:
                contents: str = handle.read()
            known: str | None = discovered.get(file_path)
            files[file_path] = known if known is not None and known == contents else contents
    return files


def discovered_sql_contents(discovered_inputs: DiscoveredProjectInputs) -> dict[Path, str]:
    """Return the text discovery read for every SQL file it retains, keyed by path."""

    contents: dict[Path, str] = {}
    for group in (
        discovered_inputs.model_files,
        discovered_inputs.enum_files,
        discovered_inputs.constant_files,
        discovered_inputs.model_schema_files,
        discovered_inputs.sql_function_files,
        discovered_inputs.sql_hook_files,
        discovered_inputs.test_files,
        discovered_inputs.scenario_files,
        discovered_inputs.audit_files,
    ):
        contents.update({item.file_path: item.contents for item in group})
    return contents


def sort_violations(violations: list) -> tuple:
    """Return violations sorted by file path then position."""

    return tuple(sorted(violations, key=lambda item: (str(item.file_path), item.line, item.column)))
