"""Build the static scope index natively."""

from __future__ import annotations

from collections.abc import Mapping

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import LoadedMacro, StaticMacroExport
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.classes.native_scope_index import NativeScopeIndex


def open_native_scope_index(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: Mapping[str, LoadedMacro],
    static_macros: tuple[StaticMacroExport, ...] = (),
) -> NativeScopeIndex:
    """Return the natively built index; discovery's normalized paths always index."""

    return NativeScopeIndex(
        native=_native.open_native_scope_index(discovered_inputs, loaded_macros, static_macros)
    )
