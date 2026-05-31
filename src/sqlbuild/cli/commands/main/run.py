"""CLI run command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_run_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.mode import enforce_direct_mode_command_support
from sqlbuild.cli.commands.main.shared.helpers.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.main.shared.helpers.plan_format import format_plan
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import (
    BuildProgressCallbacks,
    format_build_footer,
    write_execution_header,
)
from sqlbuild.cli.commands.main.shared.helpers.python_nodes import (
    load_result_key,
    python_node_result_names,
    python_node_results_failed,
    sql_loader_functions_for_lifecycle_handoff,
    task_asset_python_node_names,
    write_python_node_results,
)
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import write_runtime_target
from sqlbuild.cli.commands.main.shared.helpers.snapshot_full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.executor.python_nodes.main.region_1 import run_region_1_python_loader_nodes
from sqlbuild.executor.python_nodes.main.region_2 import create_region_2_python_execution_tracker
from sqlbuild.executor.python_nodes.models import (
    PythonNodeExecutionResult,
    Region1PythonLoaderExecutorResult,
)
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_run(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    no_color: bool = False,
    fail_fast: bool = False,
    full_refresh: bool = False,
    load_sources: bool | None = None,
    reload_sources: bool = False,
    allow_snapshot_full_refresh: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    debug: bool = False,
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the run command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    enforce_direct_mode_command_support(discovered_inputs=discovered_inputs, command_name="run")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name,
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if debug or json_output else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    should_load_sources: bool = reload_sources or (
        load_sources
        if load_sources is not None
        else build_effective_settings_config(discovered_inputs=discovered_inputs).auto_load_sources
    )
    progress_stream.write("\n")
    progress_stream.flush()
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        defer_sources_to=defer_sources_to,
        cursor_overrides=cursor_overrides,
        select=select,
        exclude=exclude,
        full_refresh=full_refresh,
        auto_load_sources=should_load_sources,
        reload_sources=reload_sources,
        connection_config=connection_config,
        cli_vars=cli_vars,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
        resolve_python_run_selectors=True,
    )

    plan_output: PlanOutput = pipeline_result.plan_output
    plan_stream: TextIO = sys.stderr if debug or json_output else sys.stdout

    plan_text: str = format_plan(
        plan_output,
        full_refresh=full_refresh,
        use_color=use_color,
        python_plan_entries=pipeline_result.python_plan_entries,
    )
    plan_stream.write("\n" + plan_text + "\n\n")
    plan_stream.flush()

    enforce_snapshot_full_refresh_policy(
        plan=plan_output,
        snapshots_config=discovered_inputs.project_config.snapshots,
        allow_snapshot_full_refresh=allow_snapshot_full_refresh,
        input_stream=sys.stdin,
        output_stream=sys.stdout,
    )

    write_compile_target(
        target_dir=effective_project_dir / "target",
        adapter=adapter,
        plan_output=plan_output,
        manifest=pipeline_result.manifest,
    )

    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=debug or json_output
    )
    effective_concurrency: int = (
        concurrency if concurrency is not None else pipeline_result.project.settings.concurrency
    )
    write_execution_header(
        stream=progress_stream,
        command="sqb run",
        target=None,
        concurrency=effective_concurrency,
        use_color=use_color,
    )

    has_external_source_loads: bool = any(
        entry.integration_kind is not None for entry in plan_output.source_load_entries
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        blank_line_before_start=has_external_source_loads,
        blank_line_after_complete=True,
        use_color=use_color,
    )

    all_task_asset_names: frozenset[str] = task_asset_python_node_names(
        selected_names=pipeline_result.python_node_names,
        discovered_inputs=discovered_inputs,
    )
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=discovered_inputs
    )
    planned_source_loader_names: frozenset[str] = frozenset(
        entry.loader
        for entry in plan_output.source_load_entries
        if entry.loader in python_graph.nodes_by_name
        and python_graph.nodes_by_name[entry.loader].kind == PythonNodeKind.LOADER
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(plan_output.upstream_deps),
            python_node_names=pipeline_result.python_node_names | planned_source_loader_names,
        ),
        python_graph=python_graph,
    )
    selected_region_1_names: frozenset[str] = lifecycle_plan.region_1_python_node_names
    region_1_connection: object | None = None
    region_1_python_results: tuple[PythonNodeExecutionResult, ...] = ()
    region_1_load_results: tuple[LoadExecutionResult, ...] = ()
    if selected_region_1_names:
        region_1_connection = adapter.connect(connection_config)
        try:
            region_1_result: Region1PythonLoaderExecutorResult = run_region_1_python_loader_nodes(
                python_graph=python_graph,
                selected_python_names=selected_region_1_names,
                loader_functions=discovered_inputs.loader_functions,
                source_map=plan_output.source_map,
                adapter=adapter,
                connection_config=connection_config,
                connection=region_1_connection,
                run_id=pipeline_result.project.run_id,
                environment=pipeline_result.project.effective_environment_name,
                vars=pipeline_result.project.effective_vars,
                is_reload=reload_sources,
                default_database=adapter.default_database(),
                default_schema=adapter.default_schema(),
                start_cursor_ts=parse_cursor_timestamp(
                    (cursor_overrides or CursorOverrides()).start_ts
                ),
                end_cursor_ts=parse_cursor_timestamp(
                    (cursor_overrides or CursorOverrides()).end_ts
                ),
                start_cursor_int=parse_cursor_integer(
                    (cursor_overrides or CursorOverrides()).start_int
                ),
                end_cursor_int=parse_cursor_integer(
                    (cursor_overrides or CursorOverrides()).end_int
                ),
                use_color=use_color,
                on_node_start=callbacks.on_node_start,
                on_node_complete=callbacks.on_node_complete,
            )
        finally:
            adapter.close(region_1_connection)
        region_1_python_results = region_1_result.python_results
        region_1_load_results = region_1_result.load_results
        write_python_node_results(
            stream=progress_stream,
            results=region_1_python_results,
            use_color=use_color,
        )
    region_2_names: frozenset[str] = (
        all_task_asset_names
        - lifecycle_plan.region_1_python_node_names
        - python_node_result_names(region_1_python_results)
    )
    region_2_connection: object | None = None
    region_2_tracker: Any | None = None
    if region_2_names:
        region_2_connection = adapter.connect(connection_config)
        region_2_tracker = create_region_2_python_execution_tracker(
            python_graph=python_graph,
            selected_python_names=region_2_names,
            adapter=adapter,
            connection_config=connection_config,
            connection=region_2_connection,
            run_id=pipeline_result.project.run_id,
            environment=pipeline_result.project.effective_environment_name,
            vars=pipeline_result.project.effective_vars,
            is_reload=reload_sources,
            default_database=adapter.default_database(),
            default_schema=adapter.default_schema(),
            start_cursor_ts=parse_cursor_timestamp(
                (cursor_overrides or CursorOverrides()).start_ts
            ),
            end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
            start_cursor_int=parse_cursor_integer(
                (cursor_overrides or CursorOverrides()).start_int
            ),
            end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
        )
        region_2_tracker.dispatch_ready_python_nodes()
        initial_region_2_results: tuple[PythonNodeExecutionResult, ...] = region_2_tracker.results
        if initial_region_2_results:
            write_python_node_results(
                stream=progress_stream,
                results=initial_region_2_results,
                use_color=use_color,
            )

    def on_node_complete_with_region_2(node_result: object) -> None:
        callbacks.on_node_complete(node_result)
        if region_2_tracker is None:
            return
        previous_names: frozenset[str] = python_node_result_names(region_2_tracker.results)
        region_2_tracker.record_sql_result(node_result)
        new_results: tuple[PythonNodeExecutionResult, ...] = tuple(
            result for result in region_2_tracker.results if result.node_name not in previous_names
        )
        if new_results:
            write_python_node_results(
                stream=progress_stream,
                results=new_results,
                use_color=use_color,
            )

    result: BuildExecutionResult
    region_1_failed: bool = any(
        load_result.status == ExecutionStatus.FAILED for load_result in region_1_load_results
    )
    if region_1_failed:
        result = BuildExecutionResult(
            status=BuildStatus.FAILED,
            load_results=region_1_load_results,
        )
    else:
        result = run_build_pipeline(
            plan=plan_output,
            connection_config=connection_config,
            adapter=adapter,
            settings=pipeline_result.project.settings,
            snapshots=discovered_inputs.project_config.snapshots,
            allow_snapshot_schema_change=allow_snapshot_schema_change,
            run_id=pipeline_result.project.run_id,
            run_tests=False,
            run_audits=False,
            fail_fast=fail_fast,
            max_concurrency=effective_concurrency,
            on_node_start=callbacks.on_node_start,
            on_node_complete=on_node_complete_with_region_2,
            on_sub_progress=callbacks.on_sub_progress,
            custom_materializations=pipeline_result.custom_materializations,
            loader_functions=sql_loader_functions_for_lifecycle_handoff(
                discovered_inputs=discovered_inputs,
                region_1_loader_names=lifecycle_plan.region_1_loader_names,
            ),
            loader_is_reload=reload_sources,
            precompleted_keys=frozenset(
                load_result_key(plan=plan_output, result=load_result)
                for load_result in region_1_load_results
            ),
            initial_load_results=region_1_load_results,
            start_cursor_ts=parse_cursor_timestamp(
                (cursor_overrides or CursorOverrides()).start_ts
            ),
            end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
            start_cursor_int=parse_cursor_integer(
                (cursor_overrides or CursorOverrides()).start_int
            ),
            end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
            on_connection_start=execution_connection_progress.on_connection_start,
            on_connection_complete=execution_connection_progress.on_connection_complete,
            on_connection_error=execution_connection_progress.on_connection_error,
            use_color=use_color,
        )
    if region_2_connection is not None:
        adapter.close(region_2_connection)
    if region_2_tracker is not None:
        finalized_region_2_results: tuple[PythonNodeExecutionResult, ...] = (
            region_2_tracker.finalize_unrun_python_nodes()
        )
        if finalized_region_2_results:
            write_python_node_results(
                stream=progress_stream,
                results=finalized_region_2_results,
                use_color=use_color,
            )
    region_2_python_results: tuple[PythonNodeExecutionResult, ...] = (
        () if region_2_tracker is None else region_2_tracker.results
    )
    python_results: tuple[PythonNodeExecutionResult, ...] = (
        *region_1_python_results,
        *region_2_python_results,
    )
    write_runtime_target(
        target_dir=effective_project_dir / "target",
        plan_output=plan_output,
        result=result,
    )

    footer: str = format_build_footer(
        result=result,
        elapsed=callbacks.elapsed,
        use_color=use_color,
        python_node_results=python_results,
    )
    progress_stream.write("\n" + footer + "\n")
    progress_stream.flush()
    write_execution_json_output(
        payload=format_run_execution_json(
            result=result,
            plan=plan_output,
            python_node_results=python_results,
        ),
        json_output=json_output,
        json_output_path=json_output_path,
    )

    python_failed: bool = python_node_results_failed(python_results)
    return 0 if result.status == BuildStatus.SUCCESS and not python_failed else 1
