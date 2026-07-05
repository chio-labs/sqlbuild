"""Shared VDE view refresh and function publish phase for executor runs."""

from __future__ import annotations

import time

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.executor.helpers.rollback import publish_function_versions
from sqlbuild.virtual.executor.main.views import refresh_logical_vde_views
from sqlbuild.virtual.executor.models import (
    VirtualEnvironmentPhysicalRelations,
    VirtualViewRefreshHooks,
)
from sqlbuild.virtual.state.models import FunctionVersionRecord


def write_virtual_environment_views(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    relations: VirtualEnvironmentPhysicalRelations,
    function_versions: dict[str, FunctionVersionRecord],
    hooks: VirtualViewRefreshHooks,
) -> None:
    """Refresh target VDE views and publish the given function versions."""

    refresh_start: float = time.perf_counter()
    if hooks.on_progress is not None:
        hooks.on_progress("Refreshing target VDE views...")
    refresh_logical_vde_views(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        physical_relations=relations.model_relations,
        seed_physical_relations=relations.seed_relations,
        on_connection_start=hooks.on_connection_start,
        on_connection_complete=hooks.on_connection_complete,
        on_connection_error=hooks.on_connection_error,
    )
    if function_versions:
        publish_function_versions(
            adapter=adapter,
            connection_config=connection_config,
            graph=graph,
            virtual_environment_name=virtual_environment_name,
            function_versions=function_versions,
        )
    if hooks.on_progress is not None:
        hooks.on_progress(
            f"Refreshed target VDE views. ({time.perf_counter() - refresh_start:.2f}s)"
        )
