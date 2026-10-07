"""The source and schema YAML files discovery reads, in Python's discovery order."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.scoped_paths import (
    is_in_scoped_declaration_tree,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import SCHEMA_FILE_NAME, YAML_FILE_SUFFIXES
from sqlbuild.compiler.discovery.exceptions import SchemaParseError


def source_file_paths(*, project_dir: Path) -> tuple[Path, ...]:
    """Return the YAML files directly below sources/, in path order."""

    sources_root: Path = project_dir / "sources"
    if not sources_root.is_dir():
        return ()
    return tuple(
        sorted(path for path in sources_root.iterdir() if path.suffix in YAML_FILE_SUFFIXES)
    )


def schema_file_paths(*, project_dir: Path) -> tuple[Path, ...]:
    """Return the unscoped model schema.yml files and seed declaration files, in Python's order."""

    tree: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    schema_paths: list[Path] = []
    models_root: Path = project_dir / "models"
    seeds_root: Path = project_dir / "seeds"

    if models_root.is_dir():
        schema_paths.extend(
            path
            for path in sorted(tree.rglob(root=models_root, pattern=SCHEMA_FILE_NAME))
            if not is_in_scoped_declaration_tree(file_path=path, project_dir=project_dir)
        )
    if seeds_root.is_dir():
        yaml_path: Path
        for yaml_path in sorted(tree.rglob(root=seeds_root, pattern="*.yaml")):
            raise SchemaParseError(
                f"Seed declaration file {yaml_path.relative_to(project_dir)} must use .yml; "
                ".yaml is not supported"
            )
        schema_paths.extend(sorted(tree.rglob(root=seeds_root, pattern="*.yml")))
    return tuple(dict.fromkeys(schema_paths))
