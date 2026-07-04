"""Build command post-build python checks phase."""

from __future__ import annotations

from typing import Any

from sqlbuild.cli.commands.helpers.build.models import (
    BuildCommandRequest,
    BuildInvocation,
    BuildRunOutcome,
)
from sqlbuild.cli.commands.helpers.check.core import (
    load_results_by_loader_name,
    record_python_run_state_results,
    relevant_check_functions,
    write_check_results,
)
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.main.checks import execute_python_checks
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeRunState,
)


def run_post_build_python_checks(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    outcome: BuildRunOutcome,
    providers: Any,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute relevant python check functions after a successful build."""

    if outcome.result.status != BuildStatus.SUCCESS:
        return ()
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=invocation.discovered_inputs
    )
    check_functions: tuple[DiscoveredCheckFunction, ...] = relevant_check_functions(
        discovered_inputs=invocation.discovered_inputs,
        python_graph=python_graph,
        exclude=request.exclude,
        selected_dependency_names=frozenset(result.node_name for result in outcome.python_results)
        | frozenset(
            load_results_by_loader_name(
                source_map=pipeline_result.plan_output.source_map,
                load_results=outcome.result.load_results,
            )
        ),
    )
    if not check_functions:
        return ()
    check_connection: object = invocation.adapter.connect(invocation.connection_config)
    check_results: tuple[PythonCheckExecutionResult, ...]
    try:
        check_run_state: PythonNodeRunState = PythonNodeRunState()
        record_python_run_state_results(
            discovered_inputs=invocation.discovered_inputs,
            run_state=check_run_state,
            python_results=outcome.python_results,
            load_results=outcome.result.load_results,
            source_map=pipeline_result.plan_output.source_map,
        )
        check_results = execute_python_checks(
            check_functions=check_functions,
            python_graph=python_graph,
            upstream_python_results=outcome.python_results,
            upstream_load_results=outcome.result.load_results,
            upstream_load_results_by_loader_name=load_results_by_loader_name(
                source_map=pipeline_result.plan_output.source_map,
                load_results=outcome.result.load_results,
            ),
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            connection=check_connection,
            run_id=pipeline_result.project.run_id,
            target=pipeline_result.project.effective_target_name,
            vars=pipeline_result.project.effective_vars,
            is_reload=request.reload_sources,
            run_state=check_run_state,
            default_database=invocation.adapter.default_database(),
            default_schema=invocation.adapter.default_schema(),
            providers=providers,
        )
    finally:
        invocation.adapter.close(check_connection)
    write_check_results(
        stream=invocation.progress_stream,
        results=check_results,
        use_color=invocation.use_color,
        check_functions=check_functions,
        python_graph=python_graph,
    )
    return check_results
