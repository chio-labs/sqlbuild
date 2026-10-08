"""Expected exceptions for the pre-semantic compile attachment layer."""

from __future__ import annotations

from sqlbuild.spec.contracts.models import SourceLocation


class CompileInputError(ValueError):
    """Raised when discovered inputs cannot be attached into a compile view."""

    code: str = "P001"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class SqlTestReferenceError(CompileInputError):
    """Raised when a SQL-test CTE calls a reference the test query cannot resolve."""

    code: str = "P013"

    def __init__(self, message: str, *, location: SourceLocation, help: str) -> None:
        super().__init__(
            f"{location.path.as_posix()}:{location.line}:{location.column}: {message}", help=help
        )
        self.location: SourceLocation = location


class MacroDeclarationLookupError(CompileInputError, KeyError):
    """Retain authored diagnostics while honoring the Mapping lookup contract."""


class NativeSqlTestResponseError(CompileInputError):
    """Raised when native SQL-test extraction returns malformed data."""


class CompactAnalysisInputError(CompileInputError):
    """Raised when compact SQL-analysis batch inputs are inconsistent."""


class AnalysisCacheEntryError(ValueError):
    """Raised when a persisted model analysis cache entry is invalid."""
