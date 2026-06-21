"""CLI check command entry point for Python checks."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.check import (
    build_check_relation_targets,
    format_check_json,
    load_results_by_loader_name,
    record_python_run_state_results,
    resolve_selected_check_names,
    run_check_read_side_dependencies,
    write_check_results,
)
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.execution_json import write_execution_json_output
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import write_execution_header
from sqlbuild.cli.commands.main.shared.helpers.runtime_target_writer import (
    write_python_check_runtime_target,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.executor.python_nodes.main.checks import execute_python_checks
from sqlbuild.executor.python_nodes.main.ingress import execute_ingress_python_loader_nodes
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonIngressLoaderExecutorResult,
    PythonNodeExecutionResult,
)
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.summary_footer import format_summary_footer
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_check(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the check command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    write_execution_header(
        stream=progress_stream,
        command="sqb check",
        target=None,
        concurrency=1,
        use_color=use_color,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        source_deferral_enabled=False,
        select=(),
        exclude=(),
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
    )
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=discovered_inputs
    )
    check_names: frozenset[str] = resolve_selected_check_names(
        graph=python_graph,
        select=select,
        exclude=exclude,
    )
    check_functions: tuple[DiscoveredCheckFunction, ...] = tuple(
        check for check in discovered_inputs.check_functions if check.name in check_names
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(),
            python_node_names=frozenset(),
        ),
        python_graph=python_graph,
    )
    relation_targets: dict[SqlResourceRef, str] = build_check_relation_targets(
        adapter=adapter,
        pipeline_result=pipeline_result,
    )
    default_database: str | None = pipeline_result.project.effective_target_database
    if default_database is None:
        default_database = adapter.default_database()
    default_schema: str | None = pipeline_result.project.effective_target_schema
    if default_schema is None:
        default_schema = adapter.default_schema()
    provider_session: Any = build_provider_session(discovered_inputs.providers)
    try:
        connection: Any = adapter.connect(connection_config)
        try:
            ingress_result: PythonIngressLoaderExecutorResult = execute_ingress_python_loader_nodes(
                python_graph=python_graph,
                selected_python_names=lifecycle_plan.ingress_python_node_names,
                loader_functions=discovered_inputs.loader_functions,
                source_map=pipeline_result.plan_output.source_map,
                adapter=adapter,
                connection_config=connection_config,
                connection=connection,
                run_id=pipeline_result.project.run_id,
                target=pipeline_result.project.effective_target_name,
                vars=pipeline_result.project.effective_vars,
                is_reload=False,
                default_database=default_database,
                default_schema=default_schema,
                use_color=use_color,
                relation_targets=relation_targets,
                providers=provider_session.providers,
            )
            record_python_run_state_results(
                discovered_inputs=discovered_inputs,
                run_state=ingress_result.run_state,
                python_results=ingress_result.python_results,
                load_results=ingress_result.load_results,
                source_map=pipeline_result.plan_output.source_map,
            )
            read_side_results: tuple[PythonNodeExecutionResult, ...] = (
                run_check_read_side_dependencies(
                    adapter=adapter,
                    connection_config=connection_config,
                    connection=connection,
                    pipeline_result=pipeline_result,
                    python_graph=python_graph,
                    lifecycle_plan=lifecycle_plan,
                    relation_targets=relation_targets,
                    providers=provider_session.providers,
                )
            )
            record_python_run_state_results(
                discovered_inputs=discovered_inputs,
                run_state=ingress_result.run_state,
                python_results=read_side_results,
                source_map=pipeline_result.plan_output.source_map,
            )
            results: tuple[PythonCheckExecutionResult, ...] = execute_python_checks(
                check_functions=check_functions,
                python_graph=python_graph,
                upstream_python_results=(*ingress_result.python_results, *read_side_results),
                upstream_load_results=ingress_result.load_results,
                upstream_load_results_by_loader_name=load_results_by_loader_name(
                    source_map=pipeline_result.plan_output.source_map,
                    load_results=ingress_result.load_results,
                ),
                adapter=adapter,
                connection_config=connection_config,
                connection=connection,
                run_id=pipeline_result.project.run_id,
                target=pipeline_result.project.effective_target_name,
                vars=pipeline_result.project.effective_vars,
                is_reload=False,
                run_state=ingress_result.run_state,
                default_database=default_database,
                default_schema=default_schema,
                relation_targets=relation_targets,
                providers=provider_session.providers,
                require_upstream_results=False,
            )
        finally:
            adapter.close(connection)
        write_check_results(
            stream=progress_stream,
            results=results,
            use_color=use_color,
            check_functions=check_functions,
            python_graph=python_graph,
        )
        pass_count: int = sum(1 for result in results if result.passed)
        warn_count: int = sum(1 for result in results if result.warned)
        fail_count: int = sum(1 for result in results if result.failed)
        progress_stream.write(
            "\n"
            + format_summary_footer(
                counts=(
                    ("PASS", pass_count),
                    ("WARN", warn_count),
                    ("FAIL", fail_count),
                    ("TOTAL", len(results)),
                ),
                use_color=use_color,
            )
            + "\n"
        )
        progress_stream.flush()
        write_python_check_runtime_target(
            target_dir=effective_project_dir / "target", results=results
        )
        write_execution_json_output(
            payload=format_check_json(results=results),
            json_output=json_output,
            json_output_path=json_output_path,
        )
        return 0 if fail_count == 0 else 1
    finally:
        provider_session.close()
