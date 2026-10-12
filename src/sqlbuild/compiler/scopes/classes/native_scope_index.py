"""A natively built scope index and the Python scope models materialised from it."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.models import ScopeIndex, ScopeLookup
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


class NativeScopeIndex:
    """One native scope index, its static index and its relationship grants."""

    def __init__(self, *, native: _native.NativeScopeIndex) -> None:
        self._native: _native.NativeScopeIndex = native
        self.index: ScopeIndex = native.index
        self.has_scoped_relationship_declarations: bool = (
            native.has_scoped_relationship_declarations
        )

    def grant_relationships(
        self,
        *,
        discovered_inputs: DiscoveredProjectInputs,
        syntax: SqlLexicalSyntax,
        scan_store: tuple[_native.SqlTestScanStore | None, str],
    ) -> tuple[tuple[Path, str], ...]:
        """Grant every test's and scenario's relationships; return each extraction fault."""

        return self._native.grant_relationships(
            discovered_inputs=discovered_inputs, syntax=syntax, scan_store=scan_store
        )

    def index_with_relationships(self) -> ScopeIndex:
        """Return the index with its grants attached and relationships complete."""

        return self._native.index_with_relationships()

    def lookup(self, *, index: ScopeIndex) -> ScopeLookup:
        """The native scope lookup of `index_with_relationships()`."""

        return _native.build_scope_lookup(index)
