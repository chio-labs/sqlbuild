"""Dagster integration errors."""

from __future__ import annotations


class DagsterIntegrationError(Exception):
    """Base error for SQLBuild Dagster integration failures."""

    code: str = "I000"

    def __init__(self, message: str, *, code: str | None = None, help: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code if code is not None else self.code
        self.help = help


class DagsterDependencyError(DagsterIntegrationError):
    """Dagster is required but not installed."""

    code: str = "I001"


class DagsterDagInputError(DagsterIntegrationError):
    """Invalid SQLBuild DAG artifact input."""

    code: str = "I002"


class DagsterProjectPrepareError(DagsterIntegrationError):
    """SQLBuild project artifact preparation failed."""

    code: str = "I003"
