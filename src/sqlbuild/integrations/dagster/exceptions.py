"""Dagster integration errors."""

from __future__ import annotations


class DagsterIntegrationError(Exception):
    """Base error for SQLBuild Dagster integration failures."""


class DagsterDependencyError(DagsterIntegrationError):
    """Dagster is required but not installed."""


class DagsterDagInputError(DagsterIntegrationError):
    """Invalid SQLBuild DAG artifact input."""


class DagsterProjectPrepareError(DagsterIntegrationError):
    """SQLBuild project artifact preparation failed."""
