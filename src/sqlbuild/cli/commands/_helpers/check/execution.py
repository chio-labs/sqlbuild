"""Check command execution phases."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.cli.commands._helpers.check.core import (
    build_check_relation_targets,
    load_results_by_loader_name,
    record_python_run_state_results,
    resolve_selected_check_names,
    run_check_read_side_dependencies,
)
from sqlbuild.cli.commands.models import (
    CheckCommandRequest,
    CheckExecutionPreparation,
    CheckInvocation,
)
from sqlbuild.cli.output.classes.execution_event_writer import ExecutionEventWriter
from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
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
    IngressCallbacks,
    PythonCheckCallbacks,
    PythonCheckExecutionResult,
    PythonIngressLoaderExecutorResult,
    PythonNodeExecutionResult,
    PythonNodeRuntime,
)
from sqlbuild.provider.classes.container import ProviderContainer
from sqlbuild.python_nodes.models import SqlResourceRef


def prepare_check_execution(
    *,
    request: CheckCommandRequest,
    invocation: CheckInvocation,
    pipeline_result: CompilePipelineResult,
) -> CheckExecutionPreparation:
    """Prepare Python graph selection and relation context for check execution."""

    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=invocation.discovered_inputs
    )
    check_names: frozenset[str] = resolve_selected_check_names(
        graph=python_graph,
        select=request.select,
        exclude=request.exclude,
    )
    check_functions: tuple[DiscoveredCheckFunction, ...] = tuple(
        check for check in invocation.discovered_inputs.check_functions if check.name in check_names
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(),
            python_node_names=frozenset(),
        ),
        python_graph=python_graph,
    )
    relation_targets: dict[SqlResourceRef, str] = build_check_relation_targets(
        adapter=invocation.adapter,
        pipeline_result=pipeline_result,
        python_graph=python_graph,
        selected_python_names=check_names,
    )
    relation_refs: frozenset[SqlResourceRef] = python_graph.selected_sql_refs(
        selected_names=check_names
    )
    return CheckExecutionPreparation(
        python_graph=python_graph,
        check_functions=check_functions,
        lifecycle_plan=lifecycle_plan,
        relation_targets=relation_targets,
        relation_refs=relation_refs,
        default_database=_default_database(invocation=invocation, pipeline_result=pipeline_result),
        default_schema=_default_schema(invocation=invocation, pipeline_result=pipeline_result),
    )


def execute_check_plan(
    *,
    invocation: CheckInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: CheckExecutionPreparation,
    providers: ProviderContainer,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute selected Python checks with their Python dependencies."""

    connection: Any = invocation.adapter.connect(invocation.connection_config)
    event_writer: ExecutionEventWriter = ExecutionEventWriter()
    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None:
        projector.configure_resources(
            ordinals={
                check.name: index
                for index, check in enumerate(preparation.check_functions, start=1)
            },
            total=len(preparation.check_functions),
        )
    on_check_complete: Callable[[PythonCheckExecutionResult], None] = _check_completion_adapter(
        event_writer=event_writer,
        pipeline_result=pipeline_result,
    )
    try:
        ingress_result: PythonIngressLoaderExecutorResult = _execute_check_ingress(
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            connection=connection,
            providers=providers,
        )
        read_side_results: tuple[PythonNodeExecutionResult, ...] = _execute_check_read_side(
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            connection=connection,
            ingress_result=ingress_result,
            providers=providers,
        )
        return execute_python_checks(
            check_functions=preparation.check_functions,
            python_graph=preparation.python_graph,
            upstream_python_results=(*ingress_result.python_results, *read_side_results),
            upstream_load_results=ingress_result.load_results,
            upstream_load_results_by_loader_name=load_results_by_loader_name(
                source_map=pipeline_result.plan_output.source_map,
                load_results=ingress_result.load_results,
            ),
            runtime=PythonNodeRuntime(
                adapter=invocation.adapter,
                connection_config=invocation.connection_config,
                connection=connection,
                run_id=pipeline_result.project.run_id,
                target=pipeline_result.project.effective_target_name,
                vars=pipeline_result.project.effective_vars,
                is_reload=False,
                default_database=preparation.default_database,
                default_schema=preparation.default_schema,
                relation_targets=preparation.relation_targets,
                providers=providers,
            ),
            run_state=ingress_result.run_state,
            require_upstream_results=False,
            callbacks=PythonCheckCallbacks(on_check_complete=on_check_complete),
        )
    finally:
        event_writer.close()
        invocation.adapter.close(connection)


def _check_completion_adapter(
    *,
    event_writer: ExecutionEventWriter,
    pipeline_result: CompilePipelineResult,
) -> Callable[[PythonCheckExecutionResult], None]:
    def _on_complete(result: PythonCheckExecutionResult) -> None:
        event_writer.write_build_result(
            result=result,
            plan=pipeline_result.plan_output,
            command="check",
        )

    return _on_complete


def _execute_check_ingress(
    *,
    invocation: CheckInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: CheckExecutionPreparation,
    connection: Any,
    providers: ProviderContainer,
) -> PythonIngressLoaderExecutorResult:
    ingress_result: PythonIngressLoaderExecutorResult = execute_ingress_python_loader_nodes(
        python_graph=preparation.python_graph,
        selected_python_names=preparation.lifecycle_plan.ingress_python_node_names,
        loader_functions=invocation.discovered_inputs.loader_functions,
        source_map=pipeline_result.plan_output.source_map,
        runtime=PythonNodeRuntime(
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            connection=connection,
            run_id=pipeline_result.project.run_id,
            target=pipeline_result.project.effective_target_name,
            vars=pipeline_result.project.effective_vars,
            is_reload=False,
            default_database=preparation.default_database,
            default_schema=preparation.default_schema,
            relation_targets=preparation.relation_targets,
            providers=providers,
        ),
        callbacks=IngressCallbacks(use_color=invocation.use_color),
    )
    record_python_run_state_results(
        discovered_inputs=invocation.discovered_inputs,
        run_state=ingress_result.run_state,
        python_results=ingress_result.python_results,
        load_results=ingress_result.load_results,
        source_map=pipeline_result.plan_output.source_map,
    )
    return ingress_result


def _execute_check_read_side(
    *,
    invocation: CheckInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: CheckExecutionPreparation,
    connection: Any,
    ingress_result: PythonIngressLoaderExecutorResult,
    providers: ProviderContainer,
) -> tuple[PythonNodeExecutionResult, ...]:
    read_side_results: tuple[PythonNodeExecutionResult, ...] = run_check_read_side_dependencies(
        adapter=invocation.adapter,
        connection_config=invocation.connection_config,
        connection=connection,
        pipeline_result=pipeline_result,
        python_graph=preparation.python_graph,
        lifecycle_plan=preparation.lifecycle_plan,
        relation_targets=preparation.relation_targets,
        validation_refs=preparation.relation_refs,
        providers=providers,
    )
    record_python_run_state_results(
        discovered_inputs=invocation.discovered_inputs,
        run_state=ingress_result.run_state,
        python_results=read_side_results,
        source_map=pipeline_result.plan_output.source_map,
    )
    return read_side_results


def _default_database(
    *, invocation: CheckInvocation, pipeline_result: CompilePipelineResult
) -> str | None:
    if pipeline_result.project.effective_target_database is not None:
        return pipeline_result.project.effective_target_database
    return invocation.adapter.default_database()


def _default_schema(
    *, invocation: CheckInvocation, pipeline_result: CompilePipelineResult
) -> str | None:
    if pipeline_result.project.effective_target_schema is not None:
        return pipeline_result.project.effective_target_schema
    return invocation.adapter.default_schema()
