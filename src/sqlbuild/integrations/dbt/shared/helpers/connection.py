"""Shared dbt interop connection resolution."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.main.profile_connection import resolve_raw_dbt_profile_connection
from sqlbuild.integrations.dbt.models import NormalizedDbtProfileConnection


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    discovered_inputs: DiscoveredProjectInputs,
) -> dict[str, object]:
    """Resolve dbt interop connection config without importing CLI helpers."""

    config: dict[str, object] = dict(raw_config)
    resolved_dbt_profile: NormalizedDbtProfileConnection | None = (
        resolve_raw_dbt_profile_connection(
            raw_config=config,
            project_dir=project_dir,
            adapter_name=adapter_name,
            project_config=discovered_inputs.project_config,
        )
    )
    if resolved_dbt_profile is not None:
        for warning in resolved_dbt_profile.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        config = resolved_dbt_profile.connection
    database: object | None = config.get("database")
    if (
        adapter_name == BuiltinAdapter.DUCKDB
        and isinstance(database, str)
        and not Path(database).is_absolute()
        and database != ":memory:"
    ):
        config["database"] = str(project_dir / database)
    return config
