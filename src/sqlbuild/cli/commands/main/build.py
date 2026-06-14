"""CLI build command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.check import (
    check_results_failed,
    load_results_by_loader_name,
    record_python_run_state_results,
    relevant_check_functions,
    write_check_results,
)
from sqlbuild.cli.commands.main.helpers.compile.target_writer import write_compile_target
from sqlbuild.cli.commands.main.helpers.source_freshness import (
    append_eligible_standard_source_freshness_records,
)
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
    python_node_results_failed,
)
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import (
    write_python_check_runtime_target,
    write_runtime_target,
)
from sqlbuild.cli.commands.main.shared.helpers.snapshot_full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.cli.commands.main.shared.helpers.standard_python_lifecycle import (
    StandardPythonLifecycleState,
    prepare_standard_python_lifecycle,
)
from sqlbuild.cli.commands.main.virtual_build import run_virtual_build
from sqlbuild.compiler.compile.main.effective_settings import build_effective_settings_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.executor.python_nodes.main.checks import execute_python_checks
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
)
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


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
    force: bool = False,
    run_tests: bool = True,
    run_audits: bool = True,
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
    provider_session: Any = build_provider_session(discovered_inputs.providers)
    try:
        if discovered_inputs.project_config.settings.virtual_environments:
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
                changes_only=not force,
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
                run_tests=run_tests,
                run_audits=run_audits,
                json_output=json_output,
                json_output_path=json_output_path,
                use_color=use_color,
                progress_stream=progress_stream,
                providers=provider_session.providers,
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
            changes_only=not force,
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
            resolve_python_run_selectors=include_python or should_load_sources,
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
        if not plan_has_executable_work(
            plan_output, python_plan_entries=pipeline_result.python_plan_entries
        ):
            return 0

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

        python_lifecycle: StandardPythonLifecycleState = prepare_standard_python_lifecycle(
            discovered_inputs=discovered_inputs,
            pipeline_result=pipeline_result,
            plan_output=plan_output,
            adapter=adapter,
            connection_config=connection_config,
            include_python=include_python,
            reload_sources=reload_sources,
            start_cursor_ts=parse_cursor_timestamp(
                (cursor_overrides or CursorOverrides()).start_ts
            ),
            end_cursor_ts=parse_cursor_timestamp((cursor_overrides or CursorOverrides()).end_ts),
            start_cursor_int=parse_cursor_integer(
                (cursor_overrides or CursorOverrides()).start_int
            ),
            end_cursor_int=parse_cursor_integer((cursor_overrides or CursorOverrides()).end_int),
            use_color=use_color,
            progress_stream=progress_stream,
            on_node_start=callbacks.on_node_start,
            on_node_complete=callbacks.on_node_complete,
            providers=provider_session.providers,
        )
        result: BuildExecutionResult = run_build_pipeline(
            plan=plan_output,
            connection_config=connection_config,
            adapter=adapter,
            settings=pipeline_result.project.settings,
            snapshots=discovered_inputs.project_config.snapshots,
            allow_snapshot_schema_change=allow_snapshot_schema_change,
            run_id=pipeline_result.project.run_id,
            run_tests=run_tests,
            run_audits=run_audits,
            fail_fast=fail_fast,
            max_concurrency=effective_concurrency,
            on_node_start=callbacks.on_node_start,
            on_node_complete=python_lifecycle.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
            custom_materializations=pipeline_result.custom_materializations,
            custom_prepare_version_functions=pipeline_result.custom_prepare_version_functions,
            loader_functions=python_lifecycle.loader_functions,
            loader_is_reload=reload_sources,
            precompleted_keys=python_lifecycle.precompleted_keys,
            initial_load_results=python_lifecycle.ingress_load_results,
            initial_failed_keys=python_lifecycle.blocked_keys,
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
            providers=provider_session.providers,
        )
        append_eligible_standard_source_freshness_records(
            plan=plan_output,
            result=result,
            adapter=adapter,
            connection_config=connection_config,
            run_id=pipeline_result.project.run_id,
        )
        python_lifecycle.finalize()
        python_results: tuple[PythonNodeExecutionResult, ...] = python_lifecycle.python_results
        check_results: tuple[PythonCheckExecutionResult, ...] = ()
        if result.status == BuildStatus.SUCCESS:
            python_graph: PythonNodeGraph = build_discovered_python_node_graph(
                discovered_inputs=discovered_inputs
            )
            check_functions: tuple[DiscoveredCheckFunction, ...] = relevant_check_functions(
                discovered_inputs=discovered_inputs,
                python_graph=python_graph,
                exclude=exclude,
                selected_dependency_names=frozenset(result.node_name for result in python_results)
                | frozenset(
                    load_results_by_loader_name(
                        source_map=plan_output.source_map,
                        load_results=result.load_results,
                    )
                ),
            )
            if check_functions:
                check_connection: object = adapter.connect(connection_config)
                try:
                    check_run_state: PythonNodeRunState = PythonNodeRunState()
                    record_python_run_state_results(
                        discovered_inputs=discovered_inputs,
                        run_state=check_run_state,
                        python_results=python_results,
                        load_results=result.load_results,
                        source_map=plan_output.source_map,
                    )
                    check_results = execute_python_checks(
                        check_functions=check_functions,
                        python_graph=python_graph,
                        upstream_python_results=python_results,
                        upstream_load_results=result.load_results,
                        upstream_load_results_by_loader_name=load_results_by_loader_name(
                            source_map=plan_output.source_map,
                            load_results=result.load_results,
                        ),
                        adapter=adapter,
                        connection_config=connection_config,
                        connection=check_connection,
                        run_id=pipeline_result.project.run_id,
                        target=pipeline_result.project.effective_target_name,
                        vars=pipeline_result.project.effective_vars,
                        is_reload=reload_sources,
                        run_state=check_run_state,
                        default_database=adapter.default_database(),
                        default_schema=adapter.default_schema(),
                        providers=provider_session.providers,
                    )
                finally:
                    adapter.close(check_connection)
                write_check_results(
                    stream=progress_stream,
                    results=check_results,
                    use_color=use_color,
                    check_functions=check_functions,
                    python_graph=python_graph,
                )
        write_runtime_target(
            target_dir=effective_project_dir / "target",
            plan_output=plan_output,
            result=result,
        )
        write_python_check_runtime_target(
            target_dir=effective_project_dir / "target",
            results=check_results,
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
            payload=format_build_execution_json(
                result=result,
                plan=plan_output,
                python_node_results=python_results,
                python_check_results=check_results,
            ),
            json_output=json_output,
            json_output_path=json_output_path,
        )

        python_failed: bool = python_node_results_failed(python_results)
        checks_failed: bool = check_results_failed(check_results)
        return (
            0
            if result.status == BuildStatus.SUCCESS and not python_failed and not checks_failed
            else 1
        )
    finally:
        provider_session.close()
