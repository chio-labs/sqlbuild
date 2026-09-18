"""CLI-specific expected exception types."""

from __future__ import annotations


class CliUserError(Exception):
    """Expected CLI-facing error that should be rendered without a traceback."""

    code: str = "C000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class QueryDiffOutcomeError(CliUserError):
    """Expected query-diff failure with an explicit outcome and exit code."""

    status: str
    exit_code: int

    def __init__(
        self,
        message: str,
        *,
        status: str,
        exit_code: int,
        code: str | None = None,
        help: str | None = None,
    ) -> None:
        super().__init__(message, code=code, help=help)
        self.status = status
        self.exit_code = exit_code


class QueryDiffIncompleteError(QueryDiffOutcomeError):
    """Safety or preflight prevented complete value evidence."""

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(
            message,
            status="incomplete",
            exit_code=2,
            code=code,
            help=help,
        )


class QueryDiffExecutionError(QueryDiffOutcomeError):
    """Setup, execution, ownership publication, or cleanup failed."""

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(
            message,
            status="execution_failed",
            exit_code=3,
            code=code,
            help=help,
        )
