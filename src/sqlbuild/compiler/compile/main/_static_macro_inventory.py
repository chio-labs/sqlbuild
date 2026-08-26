"""Compiler static macro inventory without authored module execution."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.render.macros import _inventory_project_macros
from sqlbuild.compiler.compile.models import StaticMacroInventory
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile


def inventory_project_macros(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> StaticMacroInventory:
    """Return validated AST exports and faults without executing macro modules."""

    return _inventory_project_macros(macro_files=macro_files)
