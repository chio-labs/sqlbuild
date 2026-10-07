"""The declaration layout walked and validated natively for the Python declaration collections."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import remember_declaration_file_facts
from sqlbuild.compiler.discovery._helpers.filesystem.named_declarations import (
    remember_declaration_groups,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_discovery_supported,
    native_display_prefix,
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

    if not native_discovery_supported(
        project_dir=project_dir, display_prefix=native_display_prefix(project_dir)
    ):
        return
    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    declaration_kind: DeclarationKind | None
    for index, declaration_kind in enumerate(declaration_kinds):
        layout: tuple[tuple[object, ...], tuple[object, ...]] | None = (
            _native.discover_declaration_layout(
                tree, None if declaration_kind is None else declaration_kind.value
            )
        )
        seed_snapshot_listings(project_dir=project_dir, tree=tree)
        if layout is None:
            return
        facts, groups = layout
        remember_declaration_file_facts(
            project_dir=project_dir,
            declaration_kind=declaration_kind,
            facts=(
                native_failure(facts)
                if facts[0] == NATIVE_FAILED_TAG
                else cast(list[NativeDeclarationFact], facts[1])
            ),
        )
        if index == 0:
            remember_declaration_groups(
                project_dir=project_dir,
                groups=(
                    native_failure(groups)
                    if groups[0] == NATIVE_FAILED_TAG
                    else cast(list[tuple[str, str]], groups[1])
                ),
            )
