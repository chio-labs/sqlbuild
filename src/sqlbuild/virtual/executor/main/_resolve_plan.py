"""Shared virtual plan resolution public entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.virtual.executor._helpers.build import resolve_virtual_plan as _resolve_virtual_plan
from sqlbuild.virtual.executor.models import VirtualBuildHooks, VirtualBuildOptions
from sqlbuild.virtual.planner.models import VirtualPlanOptions


def resolve_virtual_plan(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    options: VirtualPlanOptions,
    hooks: ConnectionHooks,
) -> CompilePipelineResult:
    """Resolve a build-grade virtual plan without executing or persisting it."""

    return _resolve_virtual_plan(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        options=VirtualBuildOptions(
            planning=options,
            snapshots=discovered_inputs.project_config.snapshots,
        ),
        hooks=VirtualBuildHooks(
            on_progress=hooks.on_progress,
            on_connection_start=hooks.on_connection_start,
            on_connection_complete=hooks.on_connection_complete,
            on_connection_error=hooks.on_connection_error,
        ),
    )
