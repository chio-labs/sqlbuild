"""Build the canonical static scope index from discovered project inputs."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.compile.models import LoadedMacro, StaticMacroExport
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.scopes.main._open_native_scope_index import open_native_scope_index
from sqlbuild.compiler.scopes.models import ScopeIndex


def build_scope_index(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: Mapping[str, LoadedMacro] | None = None,
    static_macros: tuple[StaticMacroExport, ...] = (),
) -> ScopeIndex:
    """Project discovery facts into a deterministic, partially valid scope index."""

    return open_native_scope_index(
        discovered_inputs=discovered_inputs,
        loaded_macros=loaded_macros or {},
        static_macros=static_macros,
    ).index
