"""Lineage helper constants."""

from __future__ import annotations

from sqlbuild.compiler.lineage.types import ColumnLineageMode

COLUMN_LINEAGE_MODE_VALUES: tuple[str, ...] = tuple(mode.value for mode in ColumnLineageMode)
RICH_LINEAGE_STATUS_MODEL_THRESHOLD: int = 100
