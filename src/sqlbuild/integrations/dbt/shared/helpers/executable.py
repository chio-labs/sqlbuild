"""Resolve the dbt executable for interop subprocess invocation."""

from __future__ import annotations

import os

from sqlbuild.integrations.dbt.constants import DBT_EXECUTABLE_ENV_VAR, DEFAULT_DBT_EXECUTABLE


def resolve_dbt_executable() -> str:
    """Return the dbt executable, honoring the DBT_EXECUTABLE override."""

    override: str | None = os.environ.get(DBT_EXECUTABLE_ENV_VAR)
    if override is not None and override.strip():
        return override.strip()
    return DEFAULT_DBT_EXECUTABLE
