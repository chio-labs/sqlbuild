"""Public static command compilation entrypoint."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.deferred_locations import (
    build_deferred_locations,
    resolve_deferred_target_config,
)
from sqlbuild.compiler.pipeline.main._compile_phase import compile_project_phase
from sqlbuild.compiler.pipeline.models import (
    CompiledProjectPhaseResult,
    CompilePipelineOptions,
    StaticCommandContext,
)
from sqlbuild.compiler.planner.main.commands._relations import resolve_static_relation_context
from sqlbuild.compiler.planner.main.commands._scope import resolve_static_command_scope
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerRelationsContext,
    PlannerScope,
    PlannerSelection,
)
from sqlbuild.spec.contracts.models import TargetConfig


def compile_static_command_context(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    relation_keys: frozenset[CompiledObjectKey] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> StaticCommandContext:
    """Run canonical compile, selector, and relation phases without build planning."""

    compiled: CompiledProjectPhaseResult = compile_project_phase(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        options=options,
        on_progress=on_progress,
    )
    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    if options.defer_to is not None:
        deferred_target: TargetConfig = resolve_deferred_target_config(
            discovered_inputs=discovered_inputs,
            defer_to=options.defer_to,
            current_target_name=compiled.project.effective_target_name,
        )
        deferred_locations = build_deferred_locations(
            project=compiled.project,
            deferred_target_config=deferred_target,
            effective_vars=compiled.project.effective_vars,
            default_schema=adapter.default_schema(),
            default_database=adapter.default_database(),
            render_qualified_name=adapter.render_qualified_name,
        )
    scope: PlannerScope = resolve_static_command_scope(
        project=compiled.project,
        selection=PlannerSelection(
            select=options.select,
            exclude=options.exclude,
            selected_keys=selected_keys,
        ),
        auto_load_sources=options.auto_load_sources,
    )
    relations: PlannerRelationsContext = resolve_static_relation_context(
        project=compiled.project,
        adapter=adapter,
        scope=scope,
        deferral=DeferralInputs(
            deferred_locations=deferred_locations,
            defer_sources_to=options.defer_sources_to,
            source_deferral_enabled=options.source_deferral_enabled,
        ),
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        relation_keys=relation_keys,
    )
    return StaticCommandContext(
        project=compiled.project,
        scope=scope,
        relations=relations,
        connection_config=compiled.connection_config,
        compile_seconds=compiled.compile_seconds,
    )
