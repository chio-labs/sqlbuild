"""The declaration layout walked and validated natively for the Python declaration collections."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.filesystem.core import remember_declaration_file_facts
from sqlbuild.compiler.discovery._helpers.filesystem.named_declarations import (
    remember_declaration_groups,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import (
    native_discovery_supported,
    native_display_prefix,
    native_project_tree,
    seed_snapshot_listings,
)
from sqlbuild.compiler.discovery.types import NativeDeclarationFact


def prepare_native_declaration_layout(*, project_dir: Path) -> None:
    """Record a natively validated declaration layout; Python rescans an invalid one to raise."""

    if not native_discovery_supported(
        project_dir=project_dir, display_prefix=native_display_prefix(project_dir)
    ):
        return
    tree: _native.NativeProjectTree = native_project_tree(project_dir)
    layout: tuple[list[NativeDeclarationFact] | None, list[tuple[str, str]] | None] | None = (
        _native.discover_declaration_layout(tree)
    )
    seed_snapshot_listings(project_dir=project_dir, tree=tree)
    if layout is None:
        return
    facts, groups = layout
    if facts is not None:
        remember_declaration_file_facts(project_dir=project_dir, facts=facts)
    if groups is not None:
        remember_declaration_groups(project_dir=project_dir, groups=groups)
