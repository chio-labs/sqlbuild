"""Build the static scope index natively for the compiler engine switch."""

from __future__ import annotations

from collections.abc import Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.classes.native_scope_index import NativeScopeIndex
from sqlbuild.compiler.scopes.classes.native_scope_rows import NativeScopeRows
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError


def open_native_scope_index(
    *, discovered_inputs: DiscoveredProjectInputs, loaded_macros: Mapping[str, LoadedMacro]
) -> NativeScopeIndex | None:
    """Return the natively built index, or None when the Python builder must run instead."""

    try:
        rows: NativeScopeRows = NativeScopeRows(
            discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
        )
    except (InvalidScopePathError, TypeError, ValueError):
        return None
    try:
        native: _native.NativeScopeIndex | None = _native.build_native_scope_index(
            rows.resources, rows.declarations
        )
    except (TypeError, UnicodeError):
        return None
    return None if native is None else NativeScopeIndex(native=native, rows=rows)
