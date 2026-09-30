"""Fact cache exceptions."""

from __future__ import annotations


class FactCachePayloadError(ValueError):
    """Raised when a stored fact payload is not a trusted value graph."""
