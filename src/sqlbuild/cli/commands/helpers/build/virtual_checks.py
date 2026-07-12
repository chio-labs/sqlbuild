"""Virtual build post-build python checks phase."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.check.core import (
    load_results_by_loader_name,
    record_python_run_state_results,
    relevant_check_functions,
    write_check_results,
)
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction, DiscoveredProjectInputs
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.main.checks import execute_python_checks
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.virtual.executor.classes.node_result_store import VirtualNodeResultStore
from sqlbuild.virtual.executor.models import VirtualBuildPipelineResult
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime


def run_post_virtual_build_checks(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    result: VirtualBuildPipelineResult,
    exclude: tuple[str, ...],
    reload_sources: bool,
    providers: ProviderContainer | None,
    stream: TextIO,
    use_color: bool,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute relevant python checks after a successful virtual build."""

    if result.execution_result.status != BuildStatus.SUCCESS:
        return ()
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
                source_map=result.display_plan_output.source_map,
                load_results=result.execution_result.load_results,
            )
        ),
    )
    if not check_functions:
        return ()
    check_results: tuple[PythonCheckExecutionResult, ...]
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
                source_map=result.display_plan_output.source_map,
            )
            check_results = execute_python_checks(
                check_functions=check_functions,
                python_graph=python_graph,
                upstream_python_results=result.python_node_results,
                upstream_load_results=result.execution_result.load_results,
                upstream_load_results_by_loader_name=load_results_by_loader_name(
                    source_map=result.display_plan_output.source_map,
                    load_results=result.execution_result.load_results,
                ),
                runtime=PythonNodeRuntime(
                    adapter=adapter,
                    connection_config=connection_config,
                    connection=check_connection,
                    run_id=result.project.run_id,
                    target=result.project.effective_target_name,
                    vars=result.project.effective_vars,
                    is_reload=reload_sources,
                    default_database=adapter.default_database(),
                    default_schema=adapter.default_schema(),
                    providers=providers,
                    result_store=check_result_store,
                ),
                run_state=check_run_state,
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
    return check_results
