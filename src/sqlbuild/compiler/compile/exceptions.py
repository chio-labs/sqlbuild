"""Expected exceptions for the pre-semantic compile attachment layer."""

from __future__ import annotations


class CompileInputError(ValueError):
    """Raised when discovered inputs cannot be attached into a compile view."""

    code: str = "P001"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class AnalysisCacheEntryError(ValueError):
    """Raised when a persisted model analysis cache entry is invalid."""
