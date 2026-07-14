"""Standard-mode Python lifecycle orchestration for build commands."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.classes.standard_python_lifecycle_state import (
    StandardPythonLifecycleState,
)
from sqlbuild.cli.commands.helpers.build.models import StandardLifecycleCallbacks
from sqlbuild.cli.commands.helpers.build.python_lifecycle_selection import (
    python_node_result_names,
    task_asset_python_node_names,
)
from sqlbuild.cli.commands.helpers.build.python_node_output import write_python_node_results
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.relation_targets import (
    build_python_relation_targets,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main.planning.loader_dag import build_intermediate_source_map
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.main.ingress import run_ingress_python_loader_nodes
from sqlbuild.executor.python_nodes.main.read_side import create_read_side_python_execution_tracker
from sqlbuild.executor.python_nodes.models import (
    CursorWindow,
    IngressCallbacks,
    PythonIngressLoaderExecutorResult,
    PythonNodeExecutionResult,
    PythonNodeRuntime,
)
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.runtime.contracts.types import NodeStartCallback
from sqlbuild.spec.contracts.models import SourceEntry


def prepare_standard_python_lifecycle(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    pipeline_result: CompilePipelineResult,
    plan_output: PlanOutput,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    include_python: bool,
    reload_sources: bool,
    cursor_window: CursorWindow,
    callbacks: StandardLifecycleCallbacks,
    providers: ProviderContainer | None = None,
) -> StandardPythonLifecycleState:
    """Execute ingress Python and prepare read-side dispatch for standard run/build."""

    start_cursor_ts: datetime | None = cursor_window.start_cursor_ts
    end_cursor_ts: datetime | None = cursor_window.end_cursor_ts
    start_cursor_int: int | None = cursor_window.start_cursor_int
    end_cursor_int: int | None = cursor_window.end_cursor_int
    use_color: bool = callbacks.use_color
    progress_stream: TextIO = callbacks.progress_stream
    on_node_start: NodeStartCallback | None = callbacks.on_node_start
    on_node_complete: Callable[[object], None] = callbacks.on_node_complete
    selected_task_asset_names: frozenset[str] = (
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
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=PythonSqlRunSelection(
            sql_keys=frozenset(plan_output.upstream_deps),
            python_node_names=pipeline_result.python_node_names,
        ),
        python_graph=python_graph,
    )
    relation_targets: dict[SqlResourceRef, str] = build_python_relation_targets(
        adapter=adapter,
        project=pipeline_result.project,
        plan_output=plan_output,
    )
    default_database: str | None = pipeline_result.project.effective_target_database
    if default_database is None:
        default_database = adapter.default_database()
    default_schema: str | None = pipeline_result.project.effective_target_schema
    if default_schema is None:
        default_schema = adapter.default_schema()
    ingress_source_map: dict[str, SourceEntry] = dict(plan_output.source_map)
    ingress_source_map.update(
        build_intermediate_source_map(
            project=pipeline_result.project,
            selected_keys=frozenset(
                CompiledObjectKey(name=loader_name, resource_type=CompiledResourceType.SOURCE)
                for loader_name in lifecycle_plan.ingress_loader_names
            ),
        )
    )
    ingress_python_results: tuple[PythonNodeExecutionResult, ...] = ()
    ingress_load_results: tuple[LoadExecutionResult, ...] = ()
    if lifecycle_plan.ingress_python_node_names:
        ingress_connection: object = adapter.connect(connection_config)
        try:
            ingress_result: PythonIngressLoaderExecutorResult = run_ingress_python_loader_nodes(
                python_graph=python_graph,
                selected_python_names=lifecycle_plan.ingress_python_node_names,
                loader_functions=discovered_inputs.loader_functions,
                source_map=ingress_source_map,
                runtime=PythonNodeRuntime(
                    adapter=adapter,
                    connection_config=connection_config,
                    connection=ingress_connection,
                    run_id=pipeline_result.project.run_id,
                    target=pipeline_result.project.effective_target_name,
                    vars=pipeline_result.project.effective_vars,
                    is_reload=reload_sources,
                    default_database=default_database,
                    default_schema=default_schema,
                    start_cursor_ts=start_cursor_ts,
                    end_cursor_ts=end_cursor_ts,
                    start_cursor_int=start_cursor_int,
                    end_cursor_int=end_cursor_int,
                    relation_targets=relation_targets,
                    providers=providers,
                ),
                callbacks=IngressCallbacks(
                    use_color=use_color,
                    on_node_start=on_node_start,
                    on_node_complete=on_node_complete,
                ),
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
        selected_task_asset_names
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
            runtime=PythonNodeRuntime(
                adapter=adapter,
                connection_config=connection_config,
                connection=read_side_connection,
                run_id=pipeline_result.project.run_id,
                target=pipeline_result.project.effective_target_name,
                vars=pipeline_result.project.effective_vars,
                is_reload=reload_sources,
                default_database=default_database,
                default_schema=default_schema,
                relation_targets=relation_targets,
                start_cursor_ts=start_cursor_ts,
                end_cursor_ts=end_cursor_ts,
                start_cursor_int=start_cursor_int,
                end_cursor_int=end_cursor_int,
                providers=providers,
            ),
        )
        for ingress_load_result in ingress_load_results:
            read_side_tracker.record_sql_result(ingress_load_result)
        read_side_tracker.dispatch_ready_python_nodes()
        initial_read_side_results: tuple[PythonNodeExecutionResult, ...] = read_side_tracker.results
        if initial_read_side_results:
            write_python_node_results(
                stream=progress_stream,
                results=initial_read_side_results,
                use_color=use_color,
            )
    return StandardPythonLifecycleState(
        plan_output=plan_output,
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        progress_stream=progress_stream,
        use_color=use_color,
        base_on_node_complete=on_node_complete,
        read_side_connection=read_side_connection,
        read_side_tracker=read_side_tracker,
        ingress_python_results=ingress_python_results,
        ingress_load_results=ingress_load_results,
        ingress_loader_names=lifecycle_plan.ingress_loader_names,
    )
