"""Compile command constants."""

from __future__ import annotations

from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode

COMPILE_LINEAGE_MODE_VALUES: tuple[str, ...] = tuple(mode.value for mode in CompileLineageMode)
