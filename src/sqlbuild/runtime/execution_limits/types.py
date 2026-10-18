"""Runtime execution-limit domain types."""

from __future__ import annotations

from enum import StrEnum


class ItemKind(StrEnum):
    """The kind of work one per-item deadline bounds."""

    TEST = "test"
    SCENARIO = "scenario"
    MODEL = "model"


class CancellationOutcome(StrEnum):
    """What SQLBuild knows about the warehouse work it cancelled at a deadline."""

    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    NOT_NEEDED = "not_needed"
