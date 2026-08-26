"""Expected scope-domain exception types."""

from __future__ import annotations


class ScopeError(ValueError):
    """Base error for invalid scope-domain input."""

    code: str = "S000"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code


class InvalidScopePathError(ScopeError):
    """Raised when a project-relative scope path is invalid."""

    code: str = "S011"


class InvalidQualifiedIdentityError(ScopeError):
    """Raised when a qualified scope identity cannot be parsed."""

    code: str = "S002"


class DuplicateScopeIdentityError(ScopeError):
    """Raised when records duplicate a canonical identity."""

    code: str = "S003"
