"""Build the static scope index natively."""

from __future__ import annotations

from collections.abc import Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.classes.native_scope_index import NativeScopeIndex
from sqlbuild.compiler.scopes.classes.native_scope_rows import NativeScopeRows
from sqlbuild.compiler.scopes.exceptions import UnindexableScopeError


def open_native_scope_index(
    *, discovered_inputs: DiscoveredProjectInputs, loaded_macros: Mapping[str, LoadedMacro]
) -> NativeScopeIndex:
    """Return the natively built index; discovery's normalized paths always index."""

    rows: NativeScopeRows = NativeScopeRows(
        discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
    )
    native: _native.NativeScopeIndex | None = _native.build_native_scope_index(
        rows.resources, rows.declarations
    )
    if native is None:
        raise UnindexableScopeError
    return NativeScopeIndex(native=native, rows=rows)
