"""Virtual build public entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.virtual.executor._helpers.build import run_virtual_build as _run_virtual_build
from sqlbuild.virtual.executor.models import (
    VirtualBuildHooks,
    VirtualBuildOptions,
    VirtualBuildPipelineResult,
)


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    options: VirtualBuildOptions | None = None,
    hooks: VirtualBuildHooks | None = None,
) -> VirtualBuildPipelineResult:
    """Execute a virtual-mode build."""

    return _run_virtual_build(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        options=options if options is not None else VirtualBuildOptions(),
        hooks=hooks if hooks is not None else VirtualBuildHooks(),
    )
