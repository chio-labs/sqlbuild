"""Expected dlt integration exception types."""

from __future__ import annotations


class DltIntegrationError(RuntimeError):
    """Raised when declarative dlt integration configuration or execution fails."""
