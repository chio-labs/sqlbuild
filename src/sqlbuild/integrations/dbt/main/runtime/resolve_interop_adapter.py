"""Resolve a dbt interop adapter."""

from pathlib import Path

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.integrations.dbt._helpers.planning.runtime import (
    resolve_dbt_interop_adapter as _resolve,
)


def resolve_dbt_interop_adapter(
    *, adapter_name: str, project_dir: Path | None = None
) -> BaseAdapter:
    """Resolve an adapter for dbt interop runtime planning."""

    return _resolve(adapter_name=adapter_name, project_dir=project_dir)
