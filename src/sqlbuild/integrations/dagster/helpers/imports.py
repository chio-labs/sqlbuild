"""Lazy Dagster imports for the optional integration."""

from __future__ import annotations

from typing import Any

from sqlbuild.integrations.dagster.exceptions import DagsterDependencyError


def load_dagster() -> Any:
    """Import Dagster or raise an actionable optional-dependency error."""

    try:
        import dagster as dg
    except ModuleNotFoundError as error:
        raise DagsterDependencyError(
            "Dagster is required for sqlbuild.integrations.dagster. "
            "Install SQLBuild with the dagster extra, e.g. `pip install sqlbuild[dagster]`."
        ) from error
    return dg
