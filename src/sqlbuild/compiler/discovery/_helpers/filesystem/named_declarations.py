"""Discovery of scopeable named declarations: audits, reusable schemas, and named hooks."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.native.declarations import native_declaration_groups
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.models import NamedDeclarationRoot
from sqlbuild.compiler.scopes.constants import (
    GLOBAL_NAMED_DECLARATION_ROOTS,
    GROUPED_NAMED_DECLARATION_ROLES,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind

_PATH_SEPARATOR: str = "/"


def named_declaration_roots(
    *, project_dir: Path, kinds: frozenset[DeclarationKind]
) -> tuple[NamedDeclarationRoot, ...]:
    """Return validated top-level and grouped declaration roots for the requested kinds."""

    roots: list[NamedDeclarationRoot] = []
    for role_parts, kind in GLOBAL_NAMED_DECLARATION_ROOTS.items():
        directory: Path = project_dir.joinpath(*role_parts)
        if kind in kinds and directory.is_dir():
            roots.append(
                NamedDeclarationRoot(
                    directory=directory,
                    relative_directory=Path(*role_parts),
                    kind=kind,
                    scope_kind=ScopeKind.GLOBAL,
                    ownership_root=None,
                    owning_path=None,
                )
            )
    for root_components, group in _declaration_groups(project_dir=project_dir):
        owning_path: Path = group.parent.relative_to(project_dir)
        for role_parts, (kind, scope_kind) in GROUPED_NAMED_DECLARATION_ROLES.items():
            directory = group.joinpath(*role_parts)
            if kind in kinds and directory.is_dir():
                roots.append(
                    NamedDeclarationRoot(
                        directory=directory,
                        relative_directory=directory.relative_to(project_dir),
                        kind=kind,
                        scope_kind=scope_kind,
                        ownership_root=Path(*root_components),
                        owning_path=owning_path,
                    )
                )
    return tuple(sorted(roots, key=lambda item: item.relative_directory.as_posix()))


def named_declaration_files(
    *, project_dir: Path, roots: tuple[NamedDeclarationRoot, ...], pattern: str
) -> Iterator[tuple[NamedDeclarationRoot, Path]]:
    """Yield every matching file below each root, paired with its root."""

    tree: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    root: NamedDeclarationRoot
    for root in roots:
        file_path: Path
        for file_path in sorted(tree.rglob(root=root.directory, pattern=pattern)):
            yield root, file_path


def _declaration_groups(*, project_dir: Path) -> tuple[tuple[tuple[str, ...], Path], ...]:
    return tuple(
        (tuple(root.split(_PATH_SEPARATOR)), project_dir / directory)
        for root, directory in native_declaration_groups(project_dir=project_dir)
    )
