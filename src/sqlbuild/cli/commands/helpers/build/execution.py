"""Build command execution preparation and pipeline phases."""

from __future__ import annotations

from typing import Any

from sqlbuild.cli.commands.helpers.build.models import (
    BuildCommandRequest,
    BuildExecutionPreparation,
    BuildInvocation,
    BuildRunOutcome,
)
from sqlbuild.cli.commands.helpers.freshness.source_freshness import (
    append_eligible_standard_source_freshness_records,
)
from sqlbuild.cli.commands.shared.helpers.config.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.core import (
    BuildProgressCallbacks,
    write_execution_header,
)
from sqlbuild.cli.commands.shared.helpers.python_nodes.standard_lifecycle import (
    prepare_standard_python_lifecycle,
)
from sqlbuild.cli.commands.shared.models import StandardLifecycleCallbacks
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildExecutionResult,
    BuildInitialState,
    BuildRuntimeParams,
)
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.shared.models import CursorWindow


def prepare_build_execution(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    providers: Any,
) -> BuildExecutionPreparation:
    """Prepare callbacks, concurrency, cursors, and the python lifecycle for execution."""

    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=pipeline_result.plan_output,
        use_color=invocation.use_color,
        verbose=request.verbose,
        debug=request.debug or request.json_output,
    )
    effective_concurrency: int = (
        request.concurrency
        if request.concurrency is not None
        else pipeline_result.project.settings.concurrency
    )
    write_execution_header(
        stream=invocation.progress_stream,
        command="sqb build",
        target=None,
        concurrency=effective_concurrency,
        use_color=invocation.use_color,
    )
    has_external_source_loads: bool = any(
        entry.integration_kind is not None
        for entry in pipeline_result.plan_output.source_load_entries
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        blank_line_before_start=has_external_source_loads,
        blank_line_after_complete=True,
        use_color=invocation.use_color,
    )
    cursor_overrides: CursorOverrides = request.cursor_overrides or CursorOverrides()
    preparation: BuildExecutionPreparation = BuildExecutionPreparation(
        callbacks=callbacks,
        effective_concurrency=effective_concurrency,
        execution_connection_progress=execution_connection_progress,
        python_lifecycle=prepare_standard_python_lifecycle(
            discovered_inputs=invocation.discovered_inputs,
            pipeline_result=pipeline_result,
            plan_output=pipeline_result.plan_output,
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            include_python=request.include_python,
            reload_sources=request.reload_sources,
            cursor_window=CursorWindow(
                start_cursor_ts=parse_cursor_timestamp(cursor_overrides.start_ts),
                end_cursor_ts=parse_cursor_timestamp(cursor_overrides.end_ts),
                start_cursor_int=parse_cursor_integer(cursor_overrides.start_int),
                end_cursor_int=parse_cursor_integer(cursor_overrides.end_int),
            ),
            callbacks=StandardLifecycleCallbacks(
                use_color=invocation.use_color,
                progress_stream=invocation.progress_stream,
                on_node_start=callbacks.on_node_start,
                on_node_complete=callbacks.on_node_complete,
            ),
            providers=providers,
        ),
        start_cursor_ts=parse_cursor_timestamp(cursor_overrides.start_ts),
        end_cursor_ts=parse_cursor_timestamp(cursor_overrides.end_ts),
        start_cursor_int=parse_cursor_integer(cursor_overrides.start_int),
        end_cursor_int=parse_cursor_integer(cursor_overrides.end_int),
    )
    return preparation


def execute_build_plan(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: BuildExecutionPreparation,
    providers: Any,
) -> BuildRunOutcome:
    """Run the build pipeline and finalize python lifecycle results."""

    result: BuildExecutionResult = run_build_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=invocation.connection_config,
        adapter=invocation.adapter,
        settings=pipeline_result.project.settings,
        runtime=BuildRuntimeParams(
            run_id=pipeline_result.project.run_id,
            runtime_dir=invocation.effective_project_dir / "target",
            snapshots=invocation.discovered_inputs.project_config.snapshots,
            allow_snapshot_schema_change=request.allow_snapshot_schema_change,
            run_tests=request.run_tests,
            run_audits=request.run_audits,
            fail_fast=request.fail_fast,
            max_concurrency=preparation.effective_concurrency,
            loader_is_reload=request.reload_sources,
            start_cursor_ts=preparation.start_cursor_ts,
            end_cursor_ts=preparation.end_cursor_ts,
            start_cursor_int=preparation.start_cursor_int,
            end_cursor_int=preparation.end_cursor_int,
            use_color=invocation.use_color,
            providers=providers,
        ),
        callbacks=BuildCallbacks(
            on_node_start=preparation.callbacks.on_node_start,
            on_node_complete=preparation.python_lifecycle.on_node_complete,
            on_sub_progress=preparation.callbacks.on_sub_progress,
            on_connection_start=preparation.execution_connection_progress.on_connection_start,
            on_connection_complete=(
                preparation.execution_connection_progress.on_connection_complete
            ),
            on_connection_error=preparation.execution_connection_progress.on_connection_error,
        ),
        customizations=BuildCustomizations(
            custom_materializations=pipeline_result.custom_materializations,
            custom_prepare_version_functions=pipeline_result.custom_prepare_version_functions,
            loader_functions=preparation.python_lifecycle.loader_functions,
        ),
        initial_state=BuildInitialState(
            precompleted_keys=preparation.python_lifecycle.precompleted_keys,
            initial_load_results=preparation.python_lifecycle.ingress_load_results,
            initial_failed_keys=preparation.python_lifecycle.blocked_keys,
        ),
    )
    append_eligible_standard_source_freshness_records(
        plan=pipeline_result.plan_output,
        result=result,
        adapter=invocation.adapter,
        connection_config=invocation.connection_config,
        run_id=pipeline_result.project.run_id,
    )
    preparation.python_lifecycle.finalize()
    return BuildRunOutcome(
        result=result,
        python_results=preparation.python_lifecycle.python_results,
    )
