"""The declaration layout walked and validated natively for the Python declaration collections."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import remember_declaration_file_facts
from sqlbuild.compiler.discovery._helpers.filesystem.named_declarations import (
    remember_declaration_groups,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_collection,
    native_failure,
    native_project_tree,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery.constants import NATIVE_FAILED_TAG
from sqlbuild.compiler.discovery.types import NativeDeclarationFact
from sqlbuild.compiler.scopes.types import DeclarationKind


def prepare_native_declaration_layout(
    *, project_dir: Path, declaration_kinds: tuple[DeclarationKind | None, ...] = (None,)
) -> None:
    """Record each requested native declaration scan, or the error it raises when read."""

    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    declaration_kind: DeclarationKind | None
    for index, declaration_kind in enumerate(declaration_kinds):
        layout: tuple[tuple[object, ...], tuple[object, ...]] | Exception = _layout(
            project_dir=project_dir, tree=tree, declaration_kind=declaration_kind
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
        facts: Iterable[NativeDeclarationFact] | Exception
        groups: Iterable[tuple[str, str]] | Exception
        if isinstance(layout, Exception):
            facts, groups = layout, layout
        else:
            facts = _rows(layout[0])
            groups = _rows(layout[1])
        remember_declaration_file_facts(
            project_dir=project_dir, declaration_kind=declaration_kind, facts=facts
        )
        if index == 0:
            remember_declaration_groups(project_dir=project_dir, groups=groups)


def _layout(
    *,
    project_dir: Path,
    tree: _native.NativeProjectTree,
    declaration_kind: DeclarationKind | None,
) -> tuple[tuple[object, ...], tuple[object, ...]] | Exception:
    """The native layout, or the error reading it raises where its first collection is read."""

    try:
        return native_collection(
            result=_native.discover_declaration_layout(
                tree, None if declaration_kind is None else declaration_kind.value
            ),
            project_dir=project_dir,
        )
    except (OSError, ValueError) as error:
        return error


def _rows[RowT](payload: tuple[object, ...]) -> list[RowT] | Exception:
    if payload[0] == NATIVE_FAILED_TAG:
        return native_failure(payload)
    return cast(list[RowT], payload[1])
