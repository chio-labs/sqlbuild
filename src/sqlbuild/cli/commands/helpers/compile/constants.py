"""Compile command constants."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.compile.types import CompileLineageMode

COMPILE_LINEAGE_MODE_VALUES: tuple[str, ...] = tuple(mode.value for mode in CompileLineageMode)
RICH_LINEAGE_STATUS_MODEL_THRESHOLD: int = 100
