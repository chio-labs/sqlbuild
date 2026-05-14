"""Full compile-and-plan pipeline producing CLI artifacts."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.main.load_macros import load_macros
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompiledRelationTarget,
    LoadedMacro,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.manifest.main.build import build_manifest
from sqlbuild.compiler.pipeline.helpers.deferred_targets import (
    build_deferred_targets,
    gather_deferred_relations,
    resolve_deferred_env,
)
from sqlbuild.compiler.pipeline.helpers.materializations import load_custom_materializations
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.shared.types import ExternalReferenceResolver
from sqlbuild.spec.models.project import EnvironmentConfig, resolve_effective_adapter_name


def run_compile_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    connection_config: dict[str, object] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    external_reference_resolver: ExternalReferenceResolver | None = None,
) -> CompilePipelineResult:
    """Run compile inputs, assembly, planning, and manifest generation."""

    effective_config: dict[str, object] = (
        connection_config
        if connection_config is not None
        else build_effective_connection_config(discovered_inputs=discovered_inputs)
    )
    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(effective_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
    try:
        return _build_result(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            connection=connection,
            no_sql_validation=no_sql_validation,
            defer_to=defer_to,
            select=select,
            exclude=exclude,
            cursor_overrides=cursor_overrides,
            full_refresh=full_refresh,
            on_progress=on_progress,
            external_reference_resolver=external_reference_resolver,
        )
    finally:
        adapter.close(connection)


def _build_result(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection: Any,
    no_sql_validation: bool,
    defer_to: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
    external_reference_resolver: ExternalReferenceResolver | None = None,
) -> CompilePipelineResult:
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        external_reference_resolver=external_reference_resolver,
    )

    deferred_targets: dict[str, CompiledRelationTarget] | None = None
    deferred_relations: dict[str, RelationInfo] | None = None
    if defer_to is not None:
        deferred_env: EnvironmentConfig = resolve_deferred_env(
            discovered_inputs=discovered_inputs,
            defer_to=defer_to,
            current_env_name=project.effective_environment_name,
        )
        deferred_targets = build_deferred_targets(
            project=project,
            deferred_env=deferred_env,
            effective_vars=project.effective_vars,
            default_schema=adapter.default_schema(),
            default_database=adapter.default_database(),
            render_qualified_name=adapter.render_qualified_name,
        )
        deferred_relations = gather_deferred_relations(
            adapter=adapter,
            connection=connection,
            deferred_targets=deferred_targets,
        )

    plan_output: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
        select=select,
        exclude=exclude,
        deferred_targets=deferred_targets,
        deferred_relations=deferred_relations,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        on_progress=on_progress,
    )
    loaded_macros: dict[str, LoadedMacro] = load_macros(discovered_inputs.macro_files)
    manifest: dict[str, object] = build_manifest(
        project=project,
        plan_output=plan_output,
        loaded_macros=loaded_macros,
        project_name=discovered_inputs.project_config.name,
        adapter_type=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        upstream_deps=plan_output.upstream_deps,
        downstream_deps=plan_output.downstream_deps,
    )

    custom_materializations: dict[str, Any] = load_custom_materializations(
        discovered_inputs.materialization_files
    )

    return CompilePipelineResult(
        project=project,
        plan_output=plan_output,
        manifest=manifest,
        custom_materializations=custom_materializations,
    )
