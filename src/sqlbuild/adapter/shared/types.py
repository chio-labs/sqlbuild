"""Adapter domain types."""

from __future__ import annotations

from enum import StrEnum


class CursorKind(StrEnum):
    TIMESTAMP = "timestamp"
    INTEGER = "integer"
