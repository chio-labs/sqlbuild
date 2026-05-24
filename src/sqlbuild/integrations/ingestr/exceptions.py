"""Expected ingestr integration exception types."""

from __future__ import annotations


class IngestrIntegrationError(RuntimeError):
    """Raised when ingestr command construction or execution fails."""
