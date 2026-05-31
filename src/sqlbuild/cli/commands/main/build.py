"""CLI build command entry point."""

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
    format_build_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.mode import enforce_no_defer_to_in_virtual_mode
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
from sqlbuild.cli.commands.main.virtual_build import run_virtual_build
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.main.relation_targets import build_python_relation_targets
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.executor.python_nodes.main.ingress import run_ingress_python_loader_nodes
from sqlbuild.executor.python_nodes.main.read_side import create_read_side_python_execution_tracker
from sqlbuild.executor.python_nodes.models import (
    PythonIngressLoaderExecutorResult,
    PythonNodeExecutionResult,
)
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.types import EnvironmentMode


def run_build(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    no_color: bool = False,
    fail_fast: bool = False,
    full_refresh: bool = False,
    virtual_env: str | None = None,
    load_sources: bool | None = None,
    reload_sources: bool = False,
    include_python: bool = True,
    allow_snapshot_full_refresh: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    verbose: bool = False,
    debug: bool = False,
    cli_vars: dict[str, object] | None = None,
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the build command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    enforce_no_defer_to_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name="build",
        defer_to=defer_to,
    )
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
    if discovered_inputs.project_config.environment_mode == EnvironmentMode.VIRTUAL:
        return run_virtual_build(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            adapter_name=adapter_name,
            connection_config=connection_config,
            no_sql_validation=no_sql_validation,
            defer_sources_to=defer_sources_to,
            cursor_overrides=cursor_overrides,
            full_refresh=full_refresh,
            virtual_environment_name=virtual_env,
            include_stale_upstreams=include_stale_upstreams,
            changes_only=changes_only,
            auto_load_sources=should_load_sources,
            reload_sources=reload_sources,
            include_python=include_python,
            select=select,
            exclude=exclude,
            fail_fast=fail_fast,
            allow_snapshot_full_refresh=allow_snapshot_full_refresh,
            allow_snapshot_schema_change=allow_snapshot_schema_change,
            concurrency=concurrency,
            verbose=verbose,
            debug=debug,
            cli_vars=cli_vars,
            json_output=json_output,
            json_output_path=json_output_path,
            use_color=use_color,
            progress_stream=progress_stream,
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
        resolve_python_run_selectors=include_python,
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
        command="sqb build",
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

    all_task_asset_names: frozenset[str] = (
        task_asset_python_node_names(
            selected_names=pipeline_result.python_node_names,
            discovered_inputs=discovered_inputs,
        )
        if include_python
        else frozenset()
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
    planned_source_loader_python_names: frozenset[str] = planned_source_loader_names | frozenset(
        upstream_name
        for loader_name in planned_source_loader_names
        for upstream_name in _python_upstream_closure(
            node_name=loader_name, python_graph=python_graph
        )
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(plan_output.upstream_deps),
            python_node_names=pipeline_result.python_node_names
            | planned_source_loader_python_names,
        ),
        python_graph=python_graph,
    )
    relation_targets: dict[SqlResourceRef, str] = build_python_relation_targets(
        adapter=adapter,
        project=pipeline_result.project,
        plan_output=plan_output,
    )
    selected_ingress_names: frozenset[str] = lifecycle_plan.ingress_python_node_names
    ingress_python_results: tuple[PythonNodeExecutionResult, ...] = ()
    ingress_load_results: tuple[LoadExecutionResult, ...] = ()
    if selected_ingress_names:
        ingress_connection: object = adapter.connect(connection_config)
        try:
            ingress_result: PythonIngressLoaderExecutorResult = run_ingress_python_loader_nodes(
                python_graph=python_graph,
                selected_python_names=selected_ingress_names,
                loader_functions=discovered_inputs.loader_functions,
                source_map=plan_output.source_map,
                adapter=adapter,
                connection_config=connection_config,
                connection=ingress_connection,
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
                relation_targets=relation_targets,
            )
        finally:
            adapter.close(ingress_connection)
        ingress_python_results = ingress_result.python_results
        ingress_load_results = ingress_result.load_results
        write_python_node_results(
            stream=progress_stream,
            results=ingress_python_results,
            use_color=use_color,
        )
    read_side_names: frozenset[str] = (
        all_task_asset_names
        - lifecycle_plan.ingress_python_node_names
        - python_node_result_names(ingress_python_results)
    )
    read_side_connection: object | None = None
    read_side_tracker: Any | None = None
    if read_side_names:
        read_side_connection = adapter.connect(connection_config)
        read_side_tracker = create_read_side_python_execution_tracker(
            python_graph=python_graph,
            selected_python_names=read_side_names,
            adapter=adapter,
            connection_config=connection_config,
            connection=read_side_connection,
            run_id=pipeline_result.project.run_id,
            environment=pipeline_result.project.effective_environment_name,
            vars=pipeline_result.project.effective_vars,
            is_reload=reload_sources,
            default_database=adapter.default_database(),
            default_schema=adapter.default_schema(),
            relation_targets=relation_targets,
            start_cursor_ts=parse_cursor_timestamp(
                (cursor_overrides or CursorOverrides()).start_ts
            ),
            end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
            start_cursor_int=parse_cursor_integer(
                (cursor_overrides or CursorOverrides()).start_int
            ),
            end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
        )
        read_side_tracker.dispatch_ready_python_nodes()
        initial_read_side_results: tuple[PythonNodeExecutionResult, ...] = read_side_tracker.results
        if initial_read_side_results:
            write_python_node_results(
                stream=progress_stream,
                results=initial_read_side_results,
                use_color=use_color,
            )

    def on_node_complete_with_read_side(node_result: object) -> None:
        callbacks.on_node_complete(node_result)
        if read_side_tracker is None:
            return
        previous_names: frozenset[str] = python_node_result_names(read_side_tracker.results)
        read_side_tracker.record_sql_result(node_result)
        new_results: tuple[PythonNodeExecutionResult, ...] = tuple(
            result for result in read_side_tracker.results if result.node_name not in previous_names
        )
        if new_results:
            write_python_node_results(
                stream=progress_stream,
                results=new_results,
                use_color=use_color,
            )

    result: BuildExecutionResult
    ingress_failed: bool = any(
        load_result.status == ExecutionStatus.FAILED for load_result in ingress_load_results
    ) or any(
        python_result.status == PythonNodeStatus.FAILED for python_result in ingress_python_results
    )
    if ingress_failed:
        result = BuildExecutionResult(
            status=BuildStatus.FAILED,
            load_results=ingress_load_results,
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
            run_tests=True,
            run_audits=True,
            fail_fast=fail_fast,
            max_concurrency=effective_concurrency,
            on_node_start=callbacks.on_node_start,
            on_node_complete=on_node_complete_with_read_side,
            on_sub_progress=callbacks.on_sub_progress,
            custom_materializations=pipeline_result.custom_materializations,
            loader_functions=sql_loader_functions_for_lifecycle_handoff(
                discovered_inputs=discovered_inputs,
                ingress_loader_names=lifecycle_plan.ingress_loader_names,
            ),
            loader_is_reload=reload_sources,
            precompleted_keys=frozenset(
                load_result_key(plan=plan_output, result=load_result)
                for load_result in ingress_load_results
            ),
            initial_load_results=ingress_load_results,
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
    if read_side_connection is not None:
        adapter.close(read_side_connection)
    if read_side_tracker is not None:
        finalized_read_side_results: tuple[PythonNodeExecutionResult, ...] = (
            read_side_tracker.finalize_unrun_python_nodes()
        )
        if finalized_read_side_results:
            write_python_node_results(
                stream=progress_stream,
                results=finalized_read_side_results,
                use_color=use_color,
            )
    read_side_python_results: tuple[PythonNodeExecutionResult, ...] = (
        () if read_side_tracker is None else read_side_tracker.results
    )
    python_results: tuple[PythonNodeExecutionResult, ...] = (
        *ingress_python_results,
        *read_side_python_results,
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
        payload=format_build_execution_json(result=result, plan=plan_output),
        json_output=json_output,
        json_output_path=json_output_path,
    )

    python_failed: bool = python_node_results_failed(python_results)
    return 0 if result.status == BuildStatus.SUCCESS and not python_failed else 1


def _python_upstream_closure(*, node_name: str, python_graph: PythonNodeGraph) -> frozenset[str]:
    names: set[str] = set()
    pending: list[str] = list(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)
