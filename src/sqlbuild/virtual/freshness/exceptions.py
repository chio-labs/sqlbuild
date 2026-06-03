"""Source freshness observation exceptions."""

from __future__ import annotations


class SourceFreshnessObservationError(ValueError):
    """Raised when source freshness cannot be observed safely."""
