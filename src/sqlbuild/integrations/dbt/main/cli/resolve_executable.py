"""Resolve the dbt executable."""

from sqlbuild.integrations.dbt._helpers.cli.runner import resolve_dbt_executable as _resolve


def resolve_dbt_executable() -> str:
    """Return the configured dbt executable."""

    return _resolve()
