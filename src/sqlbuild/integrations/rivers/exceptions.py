"""Rivers integration errors."""

from __future__ import annotations


class RiversIntegrationError(Exception):
    """Base error for SQLBuild Rivers integration failures."""

    code: str = "I000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class RiversDependencyError(RiversIntegrationError):
    """Rivers is required but not installed."""

    code: str = "I001"


class RiversDagInputError(RiversIntegrationError):
    """Invalid SQLBuild DAG artifact input."""

    code: str = "I002"


class RiversProjectPrepareError(RiversIntegrationError):
    """SQLBuild project artifact preparation failed."""

    code: str = "I003"
