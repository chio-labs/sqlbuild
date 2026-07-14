"""Load project macros for compile-time SQL expansion."""

from __future__ import annotations

from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.models.core import LoadedMacro
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile


def load_macros(macro_files: tuple[DiscoveredMacroFile, ...]) -> dict[str, LoadedMacro]:
    """Load project macro files into callable macro functions."""

    return load_project_macros(macro_files)
