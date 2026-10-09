"""Expected exceptions for the pre-semantic compile attachment layer."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.spec.contracts.models import SourceLocation


class CompileInputError(ValueError):
    """Raised when discovered inputs cannot be attached into a compile view."""

    code: str = "P001"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        help: str | None = None,
        bridge_independent: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help
        self.bridge_independent: bool = bridge_independent


class MacroArgumentError(CompileInputError):
    """Raised when one macro call's arguments do not parse; `offset` is in the expanded SQL."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        detail: str,
        help: str,
        macro_name: str,
        file_path: Path,
        offset: int,
        relative_position: tuple[int, int],
        location: SourceLocation | None = None,
    ) -> None:
        line, column = (
            (location.line, location.column) if location is not None else relative_position
        )
        scope: str = (
            f"of '@{macro_name}' in '{file_path}'" if location is not None else f"in '{file_path}'"
        )
        suffix: str = "" if location is not None else f" of the '@{macro_name}' arguments"
        super().__init__(
            f"Macro arguments {scope} {detail} at line {line}, column {column}{suffix}",
            help=help,
        )
        self.detail: str = detail
        self.macro_name: str = macro_name
        self.file_path: Path = file_path
        self.offset: int = offset
        self.relative_position: tuple[int, int] = relative_position
        self.location: SourceLocation | None = location

    def shifted(self, by: int) -> MacroArgumentError:
        """The same error, its offset moved by `by` into the enclosing SQL."""

        return MacroArgumentError(
            detail=self.detail,
            help=self.help or "",
            macro_name=self.macro_name,
            file_path=self.file_path,
            offset=self.offset + by,
            relative_position=self.relative_position,
        )

    def located(self, location: SourceLocation) -> MacroArgumentError:
        """The same error at its authored file location."""

        return MacroArgumentError(
            detail=self.detail,
            help=self.help or "",
            macro_name=self.macro_name,
            file_path=self.file_path,
            offset=self.offset,
            relative_position=self.relative_position,
            location=location,
        )


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


class SqlTestExtractionError(CompileInputError):
    """Raised when a SQL test cannot be split into CTEs; names the test and offending text."""

    def __init__(
        self,
        message: str,
        *,
        help: str | None = None,
        test_index: int = 0,
        token: str | None = None,
        token_offset: int | None = None,
    ) -> None:
        super().__init__(message, help=help)
        self.test_index = test_index
        self.token = token
        self.token_offset = token_offset


class CompactAnalysisInputError(CompileInputError):
    """Raised when compact SQL-analysis batch inputs are inconsistent."""


class AnalysisCacheEntryError(ValueError):
    """Raised when a persisted model analysis cache entry is invalid."""
