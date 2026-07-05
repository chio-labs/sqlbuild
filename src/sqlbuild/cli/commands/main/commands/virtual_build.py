"""CLI orchestration for virtual-mode build."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.check.core import (
    check_results_failed,
    load_results_by_loader_name,
    record_python_run_state_results,
    relevant_check_functions,
    write_check_results,
)
from sqlbuild.cli.commands.helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.helpers.plan.formatter import format_plan
from sqlbuild.cli.commands.shared.helpers.config.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.shared.helpers.output.execution_json import (
    format_build_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.progress.core import (
    BuildProgressCallbacks,
    format_build_footer,
    write_execution_header,
)
from sqlbuild.cli.commands.shared.helpers.progress.planning import (
    PlanningProgressReporter,
)
from sqlbuild.cli.commands.shared.helpers.python_nodes.core import write_python_node_results
from sqlbuild.cli.commands.shared.helpers.snapshots.full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.cli.commands.shared.helpers.targets.runtime import (
    write_python_check_runtime_target,
    write_runtime_target,
)
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.main.checks import execute_python_checks
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult, PythonNodeRunState
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.output.display import DisplayOptions
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.classes.node_result_store import VirtualNodeResultStore
from sqlbuild.virtual.executor.main.build import run_virtual_build as run_virtual_build_pipeline
from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks, VirtualBuildPipelineResult
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    adapter_name: str,
    connection_config: dict[str, object],
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    virtual_environment_name: str | None = None,
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    include_python: bool = True,
    seed_only: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    fail_fast: bool = False,
    allow_snapshot_full_refresh: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    verbose: bool = False,
    debug: bool = False,
    cli_vars: dict[str, object] | None = None,
    run_tests: bool = True,
    run_audits: bool = True,
    json_output: bool = False,
    json_output_path: Path | None = None,
    execution_command: str = "build",
    use_color: bool = False,
    progress_stream: TextIO | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    providers: ProviderContainer | None = None,
) -> int:
    """Execute a virtual build and render CLI output."""

    stream: TextIO = progress_stream or (sys.stderr if debug or json_output else sys.stdout)
    stream.write("\n")
    stream.flush()
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=stream,
        use_color=use_color,
    )
    callbacks_by_ref: list[BuildProgressCallbacks] = []

    def on_plan_ready(
        project: object,
        plan_output: PlanOutput,
        python_plan_entries: tuple[PythonPlanEntry, ...],
    ) -> VirtualBuildExecutionHooks:
        del project
        plan_text: str = format_plan(
            plan_output,
            full_refresh=full_refresh,
            use_color=use_color,
            display_options=DisplayOptions(max_entries_per_section=None if verbose else 50),
            python_plan_entries=python_plan_entries,
        )
        stream.write("\n" + plan_text + "\n\n")
        stream.flush()
        enforce_snapshot_full_refresh_policy(
            plan=plan_output,
            snapshots_config=discovered_inputs.project_config.snapshots,
            allow_snapshot_full_refresh=allow_snapshot_full_refresh,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        )
        write_compile_target(
            target_dir=project_dir / "target",
            adapter=adapter,
            plan_output=plan_output,
        )
        callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
            plan=plan_output,
            use_color=use_color,
            verbose=verbose,
            debug=debug or json_output,
        )
        callbacks_by_ref.append(callbacks)
        _write_execution_header(
            stream=stream,
            command=execution_command,
            concurrency=concurrency
            if concurrency is not None
            else discovered_inputs.project_config.settings.concurrency,
            use_color=use_color,
        )
        return VirtualBuildExecutionHooks(
            on_node_start=callbacks.on_node_start,
            on_node_complete=callbacks.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
        )

    result: VirtualBuildPipelineResult = run_virtual_build_pipeline(
        project_dir=project_dir,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        connection_config=connection_config,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        defer_sources_to=defer_sources_to,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        virtual_environment_name=virtual_environment_name,
        include_stale_upstreams=include_stale_upstreams,
        changes_only=changes_only,
        auto_load_sources=auto_load_sources,
        reload_sources=reload_sources,
        include_python=include_python,
        seed_only=seed_only,
        select=select,
        exclude=exclude,
        fail_fast=fail_fast,
        allow_snapshot_schema_change=allow_snapshot_schema_change,
        concurrency=concurrency,
        cli_vars=cli_vars,
        run_tests=run_tests,
        run_audits=run_audits,
        snapshots=discovered_inputs.project_config.snapshots,
        start_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).start_ts),
        end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
        start_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).start_int),
        end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
        on_plan_ready=on_plan_ready,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=external_sql_reference_resolver,
        providers=providers,
    )
    plan_output: PlanOutput = result.display_plan_output
    write_python_node_results(
        stream=stream,
        results=result.python_node_results,
        use_color=use_color,
    )
    check_results: tuple[PythonCheckExecutionResult, ...] = ()
    if result.execution_result.status == BuildStatus.SUCCESS:
        python_graph: PythonNodeGraph = build_discovered_python_node_graph(
            discovered_inputs=discovered_inputs
        )
        check_functions: tuple[DiscoveredCheckFunction, ...] = relevant_check_functions(
            discovered_inputs=discovered_inputs,
            python_graph=python_graph,
            exclude=exclude,
            selected_dependency_names=frozenset(
                python_result.node_name for python_result in result.python_node_results
            )
            | frozenset(
                load_results_by_loader_name(
                    source_map=plan_output.source_map,
                    load_results=result.execution_result.load_results,
                )
            ),
        )
        if check_functions:
            check_connection: object = adapter.connect(connection_config)
            try:
                state_config, state_backend = build_state_runtime(
                    discovered_inputs=discovered_inputs,
                    project_dir=project_dir,
                )
                check_state_connection: object = state_backend.connect(state_config.connection)
                try:
                    check_result_store: VirtualNodeResultStore = VirtualNodeResultStore(
                        backend=state_backend,
                        state_connection=check_state_connection,
                        state_schema=state_config.schema,
                        virtual_environment_name=result.virtual_environment_name,
                        target_database=adapter.default_database(),
                        target_schema=adapter.default_schema(),
                    )
                    check_run_state: PythonNodeRunState = PythonNodeRunState()
                    _ = record_python_run_state_results(
                        discovered_inputs=discovered_inputs,
                        run_state=check_run_state,
                        python_results=result.python_node_results,
                        load_results=result.execution_result.load_results,
                        source_map=plan_output.source_map,
                    )
                    check_results = execute_python_checks(
                        check_functions=check_functions,
                        python_graph=python_graph,
                        upstream_python_results=result.python_node_results,
                        upstream_load_results=result.execution_result.load_results,
                        upstream_load_results_by_loader_name=load_results_by_loader_name(
                            source_map=plan_output.source_map,
                            load_results=result.execution_result.load_results,
                        ),
                        adapter=adapter,
                        connection_config=connection_config,
                        connection=check_connection,
                        run_id=result.project.run_id,
                        target=result.project.effective_target_name,
                        vars=result.project.effective_vars,
                        is_reload=reload_sources,
                        run_state=check_run_state,
                        default_database=adapter.default_database(),
                        default_schema=adapter.default_schema(),
                        providers=providers,
                        result_store=check_result_store,
                    )
                finally:
                    state_backend.close(check_state_connection)
            finally:
                adapter.close(check_connection)
            write_check_results(
                stream=stream,
                results=check_results,
                use_color=use_color,
                check_functions=check_functions,
                python_graph=python_graph,
            )
    footer: str = format_build_footer(
        result=result.execution_result,
        elapsed=callbacks_by_ref[0].elapsed if callbacks_by_ref else 0,
        use_color=use_color,
        python_node_results=result.python_node_results,
    )
    write_runtime_target(
        target_dir=project_dir / "target",
        plan_output=plan_output,
        result=result.execution_result,
    )
    write_python_check_runtime_target(target_dir=project_dir / "target", results=check_results)
    stream.write("\n" + footer + "\n")
    stream.flush()
    write_execution_json_output(
        payload=format_build_execution_json(
            result=result.execution_result,
            plan=plan_output,
            python_node_results=result.python_node_results,
            python_check_results=check_results,
            command=execution_command,
        ),
        json_output=json_output,
        json_output_path=json_output_path,
    )
    return (
        0
        if result.execution_result.status == BuildStatus.SUCCESS
        and not check_results_failed(check_results)
        else 1
    )


def _write_execution_header(
    *, stream: TextIO, command: str, concurrency: int, use_color: bool
) -> None:
    write_execution_header(
        stream=stream,
        command=f"sqb {command}",
        target=None,
        concurrency=concurrency,
        use_color=use_color,
    )
