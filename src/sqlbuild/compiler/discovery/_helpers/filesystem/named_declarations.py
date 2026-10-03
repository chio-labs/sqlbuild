"""Discovery of scopeable named declarations: audits, reusable schemas, and named hooks."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import CANONICAL_AUTHORED_ROOTS
from sqlbuild.compiler.discovery.exceptions import DeclarationParseError
from sqlbuild.compiler.discovery.models import NamedDeclarationRoot
from sqlbuild.compiler.scopes.constants import (
    DECLARATION_GROUP_DIRECTORY,
    GLOBAL_NAMED_DECLARATION_DIRECTORIES,
    GLOBAL_NAMED_DECLARATION_ROOTS,
    GROUPED_NAMED_DECLARATION_ROLES,
    INHERITED_DECLARATION_DIRECTORIES,
    LOCAL_DECLARATION_DIRECTORIES,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind

_AUDIT_ROLE_DIRECTORY: str = "audits"
_LOCAL_AUDIT_ROLE_DIRECTORY: str = "_audits"
_SINGULAR_AUDIT_DIRECTORY: str = "singular"
_LAYOUT_MEMO_KEY: str = "named_declaration_layout"
_GROUPS_MEMO_KEY: str = "declaration_groups"
_NESTED_ROLE_DIRECTORIES: frozenset[str] = frozenset(
    {DECLARATION_GROUP_DIRECTORY}
    | INHERITED_DECLARATION_DIRECTORIES
    | LOCAL_DECLARATION_DIRECTORIES
)


def named_declaration_roots(
    *, project_dir: Path, kinds: frozenset[DeclarationKind]
) -> tuple[NamedDeclarationRoot, ...]:
    """Return validated top-level and grouped declaration roots for the requested kinds."""

    tree: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    if _LAYOUT_MEMO_KEY not in tree.memo:
        validate_named_declaration_layout(project_dir=project_dir)
        tree.memo[_LAYOUT_MEMO_KEY] = True
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


def validate_named_declaration_layout(*, project_dir: Path) -> None:
    """Reject entries that no named declaration role accepts."""

    tree: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    audits_root: Path = project_dir / _AUDIT_ROLE_DIRECTORY
    if audits_root.is_dir():
        _require_role_children(
            directory=audits_root,
            allowed=frozenset({"generic", _SINGULAR_AUDIT_DIRECTORY}),
            project_dir=project_dir,
            help_text="audit files must live in audits/generic/ or audits/singular/",
        )
    for top_level in sorted(GLOBAL_NAMED_DECLARATION_DIRECTORIES):
        directory: Path = project_dir / top_level
        if not directory.is_dir():
            continue
        for nested in sorted(tree.directories(root=directory)):
            if nested.name in _NESTED_ROLE_DIRECTORIES:
                nested_path: str = _relative(path=nested, project_dir=project_dir)
                raise DeclarationParseError(
                    f"Declaration directory {nested_path}/ is not allowed "
                    f"inside the project-wide {top_level}/ role; scoped declarations belong "
                    f"under <folder>/{DECLARATION_GROUP_DIRECTORY}/ below a resource tree"
                )
    for _root_components, group in _declaration_groups(project_dir=project_dir):
        for role_directory, allowed in (
            (group / _AUDIT_ROLE_DIRECTORY, frozenset({"generic", _SINGULAR_AUDIT_DIRECTORY})),
            (group / _LOCAL_AUDIT_ROLE_DIRECTORY, frozenset({"generic"})),
            (group / "hooks", frozenset({"sql", "python"})),
            (group / "_hooks", frozenset({"sql", "python"})),
        ):
            if not role_directory.is_dir():
                continue
            if (
                role_directory.name == _LOCAL_AUDIT_ROLE_DIRECTORY
                and (role_directory / _SINGULAR_AUDIT_DIRECTORY).exists()
            ):
                singular_path: str = _relative(
                    path=role_directory / _SINGULAR_AUDIT_DIRECTORY, project_dir=project_dir
                )
                raise DeclarationParseError(
                    f"{singular_path}/ is "
                    "invalid: singular audits are never used by name, so folder-only visibility "
                    f"has no meaning; use {DECLARATION_GROUP_DIRECTORY}/audits/singular/"
                )
            _require_role_children(
                directory=role_directory,
                allowed=allowed,
                project_dir=project_dir,
                help_text=(
                    f"{role_directory.name}/ accepts only "
                    + ", ".join(f"{name}/" for name in sorted(allowed))
                ),
            )


def _require_role_children(
    *, directory: Path, allowed: frozenset[str], project_dir: Path, help_text: str
) -> None:
    unsupported: tuple[Path, ...] = tuple(
        sorted(
            child
            for child in directory.iterdir()
            if not child.name.startswith(".") and (not child.is_dir() or child.name not in allowed)
        )
    )
    if unsupported:
        rendered: str = ", ".join(
            _relative(path=path, project_dir=project_dir) for path in unsupported
        )
        directory_path: str = _relative(path=directory, project_dir=project_dir)
        raise DeclarationParseError(
            f"Unsupported entries in {directory_path}/: {rendered}; {help_text}"
        )


def _declaration_groups(*, project_dir: Path) -> tuple[tuple[tuple[str, ...], Path], ...]:
    tree: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    cached: object = tree.memo.get(_GROUPS_MEMO_KEY)
    if cached is not None:
        return cast(tuple[tuple[tuple[str, ...], Path], ...], cached)
    groups: list[tuple[tuple[str, ...], Path]] = []
    for root_components in CANONICAL_AUTHORED_ROOTS:
        authored_root: Path = project_dir.joinpath(*root_components)
        if not authored_root.is_dir():
            continue
        groups.extend(
            (root_components, group)
            for group in sorted(tree.rglob(root=authored_root, pattern=DECLARATION_GROUP_DIRECTORY))
            if group.is_dir() and group.parent != authored_root
        )
    result: tuple[tuple[tuple[str, ...], Path], ...] = tuple(groups)
    tree.memo[_GROUPS_MEMO_KEY] = result
    return result


def _relative(*, path: Path, project_dir: Path) -> str:
    return path.relative_to(project_dir).as_posix()
