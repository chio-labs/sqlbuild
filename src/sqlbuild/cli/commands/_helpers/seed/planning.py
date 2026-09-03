"""Seed command plan compilation phase."""

from __future__ import annotations

from typing import Any

from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.models import (
    SeedCommandRequest,
    SeedExecutionPreparation,
    SeedInvocation,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.compiler.compile.models import CompiledSeed
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.pipeline.main.static_command import compile_static_command_context
from sqlbuild.compiler.pipeline.main.static_result import build_static_pipeline_result
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
    StaticCommandContext,
)
from sqlbuild.compiler.planner.main.commands.seed import build_seed_command_plan
from sqlbuild.compiler.planner.main.commands.seed_state import read_selected_seed_fingerprints
from sqlbuild.runtime.contracts.main.open_connection import open_connection_with_hooks
from sqlbuild.runtime.contracts.models import ConnectionHooks


def prepare_seed_execution(
    *, request: SeedCommandRequest, invocation: SeedInvocation
) -> SeedExecutionPreparation:
    """Compile seed plan and resolve effective concurrency."""

    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    invocation.progress_stream.write("\n")
    invocation.progress_stream.flush()
    options: CompilePipelineOptions = CompilePipelineOptions(
        selected_target=request.selected_target,
        select=request.select,
        exclude=request.exclude,
        connection_config=invocation.connection_config,
        cli_vars=request.cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
        ),
    )
    context: StaticCommandContext = compile_static_command_context(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=options,
    )
    selected_seeds: tuple[CompiledSeed, ...] = tuple(
        seed for seed in context.project.seeds if seed.key in context.scope.selected_keys
    )
    hooks: ConnectionHooks = ConnectionHooks(
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=lambda connection_count, elapsed_seconds: (
            connection_progress.on_connection_complete(
                connection_count=connection_count, elapsed_seconds=elapsed_seconds
            )
        ),
        on_connection_error=lambda connection_count, elapsed_seconds: (
            connection_progress.on_connection_error(
                connection_count=connection_count, elapsed_seconds=elapsed_seconds
            )
        ),
    )
    fingerprints: dict[str, Fingerprint] = {}
    if selected_seeds:
        connection: Any = open_connection_with_hooks(
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            hooks=hooks,
        )
        try:
            fingerprints = read_selected_seed_fingerprints(
                adapter=invocation.adapter,
                connection=connection,
                seeds=selected_seeds,
            )
        finally:
            invocation.adapter.close(connection)
    pipeline_result: CompilePipelineResult = build_static_pipeline_result(
        context=context,
        plan_output=build_seed_command_plan(
            project=context.project,
            scope=context.scope,
            relations=context.relations,
            fingerprints=fingerprints,
        ),
    )
    effective_concurrency: int = max(
        1,
        request.concurrency
        if request.concurrency is not None
        else pipeline_result.project.settings.concurrency,
    )
    return SeedExecutionPreparation(
        pipeline_result=pipeline_result,
        effective_concurrency=effective_concurrency,
    )
