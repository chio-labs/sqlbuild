"""Node source watermark type declarations."""

from __future__ import annotations

from enum import StrEnum


class WatermarkGraphResourceKind(StrEnum):
    MODEL = "model"
    SOURCE = "source"
    SEED = "seed"
    FUNCTION = "function"
    TEST = "test"


class WatermarkStalenessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"
