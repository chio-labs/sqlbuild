"""The declaration layout walked and validated natively for the declaration collections."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_collection,
    native_failure,
    native_project_tree,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import NATIVE_FAILED_TAG
from sqlbuild.compiler.discovery.types import NativeDeclarationFact
from sqlbuild.compiler.scopes.types import DeclarationKind

_LAYOUT_MEMO_KEY: str = "native_declaration_layout"
_GROUPS_MEMO_KEY: str = "native_declaration_groups"


def native_declaration_file_facts(
    *, project_dir: Path, declaration_kind: DeclarationKind | None
) -> list[NativeDeclarationFact]:
    """Return the declaration files of one kind (or every kind), raising an invalid layout."""

    facts, _groups = _layout(project_dir=project_dir, declaration_kind=declaration_kind)
    return cast(list[NativeDeclarationFact], _rows(facts))


def native_declaration_groups(*, project_dir: Path) -> list[tuple[str, str]]:
    """Return the `(canonical root, group directory)` pairs of a valid named layout."""

    snapshot: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    groups: object = snapshot.memo.get(_GROUPS_MEMO_KEY)
    if groups is None:
        _facts, groups = _layout(project_dir=project_dir, declaration_kind=None)
    return cast(list[tuple[str, str]], _rows(cast(tuple[object, ...], groups)))


def _layout(
    *, project_dir: Path, declaration_kind: DeclarationKind | None
) -> tuple[tuple[object, ...], tuple[object, ...]]:
    snapshot: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    memo_key: tuple[str, DeclarationKind | None] = (_LAYOUT_MEMO_KEY, declaration_kind)
    cached: object = snapshot.memo.get(memo_key)
    if cached is not None:
        return cast(tuple[tuple[object, ...], tuple[object, ...]], cached)
    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    layout: tuple[tuple[object, ...], tuple[object, ...]] = native_collection(
        result=_native.discover_declaration_layout(
            tree, None if declaration_kind is None else declaration_kind.value
        ),
        project_dir=project_dir,
    )
    seed_snapshot_listings(project_dir=project_dir, tree=tree)
    snapshot.memo[memo_key] = layout
    _ = snapshot.memo.setdefault(_GROUPS_MEMO_KEY, layout[1])
    return layout


def _rows(payload: tuple[object, ...]) -> object:
    if payload[0] == NATIVE_FAILED_TAG:
        raise native_failure(payload)
    return payload[1]
