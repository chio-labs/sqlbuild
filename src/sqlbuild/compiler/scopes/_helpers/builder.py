"""Tolerant scope snapshots built by the native scope index from partial discovery."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM
from sqlbuild.compiler.compile.main._static_macro_inventory import inventory_project_macros
from sqlbuild.compiler.compile.models import StaticMacroInventory
from sqlbuild.compiler.discovery.main._scope_snapshot import discover_scope_snapshot
from sqlbuild.compiler.discovery.models import TolerantScopeDiscovery
from sqlbuild.compiler.scopes.main._open_native_scope_index import open_native_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


def build_tolerant_scope_index(
    *, project_dir: Path, sql_lexical_syntax: SqlLexicalSyntax
) -> ScopeIndex:
    """Build a partial static index from published tolerant compiler facts."""

    snapshot: TolerantScopeDiscovery = discover_scope_snapshot(project_dir=project_dir)
    macro_inventory: StaticMacroInventory = inventory_project_macros(
        macro_files=snapshot.discovered_inputs.macro_files
    )
    native: _native.NativeScopeIndex = open_native_scope_index(
        discovered_inputs=snapshot.discovered_inputs,
        loaded_macros={},
        static_macros=macro_inventory.exports,
    )
    relationship_faults: tuple[tuple[Path, str], ...] = native.grant_relationships(
        discovered_inputs=snapshot.discovered_inputs,
        syntax=sql_lexical_syntax,
        scan_store=(None, SQL_TEST_EXPECTED_MODELS_SCAN_ALGORITHM),
    )
    return _native.scope_tolerant_index(
        native.index_with_relationships(),
        snapshot,
        (macro_inventory.faults, relationship_faults),
    )
