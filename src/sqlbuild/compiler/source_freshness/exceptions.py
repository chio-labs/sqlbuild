"""Direct source freshness state exceptions."""

from __future__ import annotations


class SourceFreshnessInputError(ValueError):
    """Raised when persisted source freshness state cannot be read safely."""


class SourceFreshnessObservationError(ValueError):
    """Raised when source freshness cannot be observed safely."""
