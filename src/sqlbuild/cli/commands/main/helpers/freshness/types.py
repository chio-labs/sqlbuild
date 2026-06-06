"""Source freshness command types."""

from __future__ import annotations

from enum import StrEnum


class FreshnessSourceStatus(StrEnum):
    """Command status for one source freshness observation."""

    OBSERVED = "observed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    TOLERATED = "tolerated"
    UNKNOWN = "unknown"
    ERROR = "error"
