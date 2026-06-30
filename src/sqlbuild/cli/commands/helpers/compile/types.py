"""Compile command types."""

from __future__ import annotations

from enum import StrEnum


class CompileLineageMode(StrEnum):
    """Column lineage mode for compile output."""

    FAST = "fast"
    RICH = "rich"
    NONE = "none"
