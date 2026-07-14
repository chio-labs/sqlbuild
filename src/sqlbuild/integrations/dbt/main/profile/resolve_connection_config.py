"""Resolve dbt interop connection configuration."""

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt._helpers.profile.connection import (
    resolve_connection_config as _resolve,
)


def resolve_connection_config(
    *,
    raw_config: dict[str, object],
    project_dir: Path,
    adapter_name: str,
    discovered_inputs: DiscoveredProjectInputs,
) -> dict[str, object]:
    """Resolve connection configuration for dbt interop."""

    return _resolve(
        raw_config=raw_config,
        project_dir=project_dir,
        adapter_name=adapter_name,
        discovered_inputs=discovered_inputs,
    )
