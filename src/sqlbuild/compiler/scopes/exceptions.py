"""Expected scope-domain exception types."""

from __future__ import annotations

from sqlbuild.compiler.scopes.models import ScopeDiagnostic


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


class ScopeCacheDecodeError(ScopeError):
    """Raised when a persistent scope-index payload is malformed."""


class ScopeValidationError(ScopeError):
    """Aggregate error raised only when strict scope validation is requested."""

    def __init__(self, diagnostics: tuple[ScopeDiagnostic, ...]) -> None:
        self.diagnostics = diagnostics
        message: str = "Invalid declaration scope index:\n" + "\n".join(
            f"[{diagnostic.code.value}] {diagnostic.message}" for diagnostic in diagnostics
        )
        super().__init__(message)
