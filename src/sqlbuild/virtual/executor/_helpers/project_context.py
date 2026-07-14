"""Shared project graph and target-context phase for virtual executor runs."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.spec.resolution.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.resolution.main.resolve_target_name import resolve_target_name
from sqlbuild.virtual.executor.models import VirtualProjectContext


def resolve_virtual_project_context(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    no_sql_validation: bool,
    cli_vars: dict[str, object] | None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    on_progress: Callable[[str], None] | None,
) -> VirtualProjectContext:
    """Compile the project graph and resolve active target VDE naming."""

    compile_start: float = time.perf_counter()
    if on_progress is not None:
        on_progress("Compiling project...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    return VirtualProjectContext(
        graph=graph,
        unsuffixed_virtual_environment_name=_resolve_unsuffixed_virtual_environment_name(
            discovered_inputs
        ),
    )


def _resolve_unsuffixed_virtual_environment_name(
    discovered_inputs: DiscoveredProjectInputs,
) -> str | None:
    active_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    if active_target_name is None:
        return None
    return resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=active_target_name,
    ).state.unsuffixed_virtual_env
