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
            selected_target=options.selected_target,
            no_sql_validation=options.no_sql_validation,
            defer_sources_to=options.defer_sources_to,
            cursor_overrides=options.cursor_overrides,
            full_refresh=options.full_refresh,
            virtual_environment_name=options.virtual_environment_name,
            include_stale_upstreams=options.include_stale_upstreams,
            changes_only=options.changes_only,
            auto_load_sources=options.auto_load_sources,
            reload_sources=options.reload_sources,
            include_python=options.include_python,
            select=options.select,
            exclude=options.exclude,
            cli_vars=options.cli_vars,
            snapshots=discovered_inputs.project_config.snapshots,
            external_sql_reference_resolver=options.external_sql_reference_resolver,
        ),
        hooks=VirtualBuildHooks(
            on_progress=hooks.on_progress,
            on_connection_start=hooks.on_connection_start,
            on_connection_complete=hooks.on_connection_complete,
            on_connection_error=hooks.on_connection_error,
        ),
    )
