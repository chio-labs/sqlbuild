"""Command-group warehouse public entry for cross-domain orchestration."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.runtime.warehouses import (
    apply_command_warehouse as _apply_command_warehouse,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def apply_command_warehouse(
    *,
    config: dict[str, object],
    adapter_name: str,
    project_dir: Path | None,
    discovered_inputs: DiscoveredProjectInputs | None,
    selected_target: str | None,
) -> dict[str, object]:
    """Return connection config whose warehouse follows the active command's group."""

    return _apply_command_warehouse(
        config=config,
        adapter_name=adapter_name,
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
    )
