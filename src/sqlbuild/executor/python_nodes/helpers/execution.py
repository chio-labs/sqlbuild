"""Serial executor helpers for Python task and asset nodes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredAssetFunction
from sqlbuild.compiler.python_nodes.types import (
    PythonNodeFanInAction,
    PythonNodeKind,
    PythonNodeStatus,
)
from sqlbuild.executor.python_nodes.helpers.results import (
    build_python_node_failure_result,
    evaluate_python_node_fan_in,
    normalize_python_node_return,
)
from sqlbuild.executor.python_nodes.models import (
    AssetContext,
    PythonNodeExecutionResult,
    PythonNodeExecutorResult,
    PythonNodeFanInDecision,
    PythonNodeRunState,
    TaskContext,
)
from sqlbuild.executor.python_nodes.types import ExecutablePythonNode
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.helpers.python_node_scheduler import (
    build_python_node_in_degree,
    build_python_node_ready_queue,
    unlock_downstream_python_nodes,
)


def execute_python_nodes(
    *,
    nodes: tuple[ExecutablePythonNode, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None = None,
    default_schema: str | None = None,
    logger: logging.Logger | None = None,
    run_state: PythonNodeRunState | None = None,
) -> PythonNodeExecutorResult:
    """Execute task/asset nodes in dependency order within the current process."""

    resolved_run_state: PythonNodeRunState = (
        run_state if run_state is not None else PythonNodeRunState()
    )
    node_by_name: dict[str, ExecutablePythonNode] = {node.name: node for node in nodes}
    node_by_function: dict[Callable[..., object], ExecutablePythonNode] = {
        node.function: node for node in nodes
    }
    upstream_names: dict[str, tuple[str, ...]] = _build_upstream_names(
        nodes=nodes,
        node_by_function=node_by_function,
    )
    downstream_names: dict[str, tuple[str, ...]] = _build_downstream_names(
        node_names=tuple(node.name for node in nodes),
        upstream_names=upstream_names,
    )
    in_degree: dict[str, int] = build_python_node_in_degree(
        node_names=tuple(node.name for node in nodes),
        upstream_names=upstream_names,
    )
    ready: list[str] = build_python_node_ready_queue(
        node_names=tuple(node.name for node in nodes),
        in_degree=in_degree,
    )
    results_by_name: dict[str, PythonNodeExecutionResult] = {}
    ordered_results: list[PythonNodeExecutionResult] = []

    while ready:
        node_name: str = ready.pop(0)
        node: ExecutablePythonNode = node_by_name[node_name]
        result: PythonNodeExecutionResult = _execute_ready_node(
            node=node,
            upstream_results=tuple(results_by_name[name] for name in upstream_names[node.name]),
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            run_id=run_id,
            environment=environment,
            vars=vars,
            is_reload=is_reload,
            statement_recorder=statement_recorder,
            default_database=default_database,
            default_schema=default_schema,
            logger=logger,
            run_state=resolved_run_state,
        )
        resolved_run_state.record_result(node_function=node.function, result=result)
        results_by_name[node.name] = result
        ordered_results.append(result)
        unlock_downstream_python_nodes(
            completed_node_name=node.name,
            in_degree=in_degree,
            ready=ready,
            downstream_names=downstream_names,
        )

    if len(ordered_results) != len(nodes):
        raise ExecutorInputError("Python node executor could not resolve all dependencies")
    return PythonNodeExecutorResult(
        results=tuple(ordered_results),
        run_state=resolved_run_state,
    )


def _execute_ready_node(
    *,
    node: ExecutablePythonNode,
    upstream_results: tuple[PythonNodeExecutionResult, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None,
    default_schema: str | None,
    logger: logging.Logger | None,
    run_state: PythonNodeRunState,
) -> PythonNodeExecutionResult:
    node_kind: PythonNodeKind = _node_kind(node)
    decision: PythonNodeFanInDecision = evaluate_python_node_fan_in(
        upstream_results=upstream_results
    )
    if decision.action == PythonNodeFanInAction.SKIP:
        return PythonNodeExecutionResult(
            node_name=node.name,
            kind=node_kind,
            status=PythonNodeStatus.SKIPPED,
            skip_reason=decision.reason,
        )
    if decision.action == PythonNodeFanInAction.BLOCK:
        return PythonNodeExecutionResult(
            node_name=node.name,
            kind=node_kind,
            status=PythonNodeStatus.FAILED,
            error_message=decision.reason,
        )
    context: TaskContext | AssetContext = _build_context(
        node=node,
        node_kind=node_kind,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        environment=environment,
        vars=vars,
        is_reload=is_reload,
        statement_recorder=statement_recorder,
        default_database=default_database,
        default_schema=default_schema,
        logger=logger,
        run_state=run_state,
    )
    try:
        returned: object = node.function(context)
    except Exception as error:
        return build_python_node_failure_result(
            node_name=node.name,
            kind=node_kind,
            error=error,
        )
    return normalize_python_node_return(
        node_name=node.name,
        kind=node_kind,
        returned=returned,
    )


def _build_context(
    *,
    node: ExecutablePythonNode,
    node_kind: PythonNodeKind,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None,
    default_schema: str | None,
    logger: logging.Logger | None,
    run_state: PythonNodeRunState,
) -> TaskContext | AssetContext:
    context_logger: logging.Logger = logger or logging.getLogger(
        f"sqlbuild.{node_kind.value}.{node.name}"
    )
    if node_kind == PythonNodeKind.ASSET:
        return AssetContext(
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            run_id=run_id,
            environment=environment,
            vars=vars,
            is_reload=is_reload,
            logger=context_logger,
            statement_recorder=statement_recorder,
            run_state=run_state,
            default_database=default_database,
            default_schema=default_schema,
        )
    return TaskContext(
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        environment=environment,
        vars=vars,
        is_reload=is_reload,
        logger=context_logger,
        statement_recorder=statement_recorder,
        run_state=run_state,
        default_database=default_database,
        default_schema=default_schema,
    )


def _build_upstream_names(
    *,
    nodes: tuple[ExecutablePythonNode, ...],
    node_by_function: dict[Callable[..., object], ExecutablePythonNode],
) -> dict[str, tuple[str, ...]]:
    upstream_names: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        names: list[str] = []
        dependency: Callable[..., object]
        for dependency in node.depends_on:
            upstream_node: ExecutablePythonNode | None = node_by_function.get(dependency)
            if upstream_node is None:
                raise ExecutorInputError(
                    f"Python node '{node.name}' depends on a node outside the executor selection"
                )
            names.append(upstream_node.name)
        upstream_names[node.name] = tuple(names)
    return upstream_names


def _build_downstream_names(
    *, node_names: tuple[str, ...], upstream_names: dict[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    downstream: dict[str, list[str]] = {node_name: [] for node_name in node_names}
    node_name: str
    upstreams: tuple[str, ...]
    for node_name, upstreams in upstream_names.items():
        upstream_name: str
        for upstream_name in upstreams:
            downstream[upstream_name].append(node_name)
    return {node_name: tuple(names) for node_name, names in downstream.items()}


def _node_kind(node: ExecutablePythonNode) -> PythonNodeKind:
    if isinstance(node, DiscoveredAssetFunction):
        return PythonNodeKind.ASSET
    return PythonNodeKind.TASK
