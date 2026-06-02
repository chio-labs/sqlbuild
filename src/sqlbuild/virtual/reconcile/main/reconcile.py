"""Virtual reconcile public entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.reconcile.helpers.reconcile import (
    run_virtual_reconcile as _run_virtual_reconcile,
)


def run_virtual_reconcile(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_target_name: str | None,
    command: str | None,
    model_name: str | None,
    physical_relation_name: str | None,
) -> str:
    """Inspect or repair virtual reconcile state."""

    return _run_virtual_reconcile(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        virtual_target_name=virtual_target_name,
        command=command,
        model_name=model_name,
        physical_relation_name=physical_relation_name,
    )
