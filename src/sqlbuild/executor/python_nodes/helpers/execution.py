"""Serial executor helpers for Python task and asset nodes."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.assets import get_asset_definition
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
from sqlbuild.shared.models import AssetDefinition, RetryPolicy, SqlResourceRef, TaskDefinition
from sqlbuild.tasks import get_task_definition


def execute_python_nodes(
    *,
    nodes: tuple[ExecutablePythonNode, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None = None,
    default_schema: str | None = None,
    relation_targets: dict[SqlResourceRef, str] | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    logger: logging.Logger | None = None,
    run_state: PythonNodeRunState | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> PythonNodeExecutorResult:
    """Execute task/asset nodes in dependency order within the current process."""

    resolved_run_state: PythonNodeRunState = (
        run_state if run_state is not None else PythonNodeRunState()
    )
    node_by_name: dict[str, ExecutablePythonNode] = {node.name: node for node in nodes}
    node_by_dependency_key: dict[object | tuple[str, str], ExecutablePythonNode] = {
        node.function: node for node in nodes
    }
    for node in nodes:
        node_by_dependency_key[("name", node.name)] = node
    upstream_names: dict[str, tuple[str, ...]] = _build_upstream_names(
        nodes=nodes,
        node_by_dependency_key=node_by_dependency_key,
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
            target=target,
            vars=vars,
            is_reload=is_reload,
            statement_recorder=statement_recorder,
            default_database=default_database,
            default_schema=default_schema,
            relation_targets={} if relation_targets is None else relation_targets,
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
            logger=logger,
            run_state=resolved_run_state,
            sleep=sleep,
            monotonic=monotonic,
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


def execute_ready_python_node(
    *,
    node: ExecutablePythonNode,
    upstream_results: tuple[PythonNodeExecutionResult, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None = None,
    default_schema: str | None = None,
    relation_targets: dict[SqlResourceRef, str] | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    logger: logging.Logger | None = None,
    run_state: PythonNodeRunState | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> PythonNodeExecutionResult:
    """Execute one scheduler-ready task/asset node."""

    return _execute_ready_node(
        node=node,
        upstream_results=upstream_results,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        statement_recorder=statement_recorder,
        default_database=default_database,
        default_schema=default_schema,
        relation_targets={} if relation_targets is None else relation_targets,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        logger=logger,
        run_state=run_state if run_state is not None else PythonNodeRunState(),
        sleep=sleep,
        monotonic=monotonic,
    )


def _execute_ready_node(
    *,
    node: ExecutablePythonNode,
    upstream_results: tuple[PythonNodeExecutionResult, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None,
    default_schema: str | None,
    relation_targets: dict[SqlResourceRef, str],
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    logger: logging.Logger | None,
    run_state: PythonNodeRunState,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
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
            skip_mode=decision.skip_mode,
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
        target=target,
        vars=vars,
        is_reload=is_reload,
        statement_recorder=statement_recorder,
        default_database=default_database,
        default_schema=default_schema,
        relation_targets=relation_targets,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        logger=logger,
        run_state=run_state,
    )
    try:
        returned: object = _call_node_with_retry(
            node=node,
            context=context,
            retry_policy=node.retry,
            sleep=sleep,
            monotonic=monotonic,
        )
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


def _call_node_with_retry(
    *,
    node: ExecutablePythonNode,
    context: TaskContext | AssetContext,
    retry_policy: RetryPolicy | None,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> object:
    if retry_policy is None:
        return node.function(context)
    start_time: float = monotonic()
    attempt: int = 1
    while True:
        try:
            return node.function(context)
        except retry_policy.retry_on:
            if attempt >= retry_policy.max_attempts:
                raise
            delay_seconds: float = _retry_delay_seconds(
                retry_policy=retry_policy,
                retry_index=attempt - 1,
            )
            if retry_policy.max_elapsed_seconds is not None:
                elapsed_seconds: float = monotonic() - start_time
                if elapsed_seconds + delay_seconds > retry_policy.max_elapsed_seconds:
                    raise
            sleep(delay_seconds)
            attempt += 1


def _retry_delay_seconds(*, retry_policy: RetryPolicy, retry_index: int) -> float:
    delay_seconds: float = retry_policy.initial_delay_seconds * (
        retry_policy.backoff_multiplier**retry_index
    )
    if retry_policy.max_delay_seconds is not None:
        delay_seconds = min(delay_seconds, retry_policy.max_delay_seconds)
    if retry_policy.jitter:
        return random.uniform(0, delay_seconds)
    return delay_seconds


def _build_context(
    *,
    node: ExecutablePythonNode,
    node_kind: PythonNodeKind,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None,
    default_schema: str | None,
    relation_targets: dict[SqlResourceRef, str],
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
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
            target=target,
            vars=vars,
            is_reload=is_reload,
            logger=context_logger,
            statement_recorder=statement_recorder,
            run_state=run_state,
            default_database=default_database,
            default_schema=default_schema,
            relation_targets=relation_targets,
            allowed_sql_refs=frozenset(
                dependency
                for dependency in node.depends_on
                if isinstance(dependency, SqlResourceRef)
            ),
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
        )
    return TaskContext(
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        logger=context_logger,
        statement_recorder=statement_recorder,
        run_state=run_state,
        default_database=default_database,
        default_schema=default_schema,
        relation_targets=relation_targets,
        allowed_sql_refs=frozenset(
            dependency for dependency in node.depends_on if isinstance(dependency, SqlResourceRef)
        ),
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
    )


def _build_upstream_names(
    *,
    nodes: tuple[ExecutablePythonNode, ...],
    node_by_dependency_key: dict[object | tuple[str, str], ExecutablePythonNode],
) -> dict[str, tuple[str, ...]]:
    upstream_names: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        names: list[str] = []
        dependency: Callable[..., object] | SqlResourceRef
        for dependency in node.depends_on:
            if isinstance(dependency, SqlResourceRef):
                continue
            upstream_node: ExecutablePythonNode | None = node_by_dependency_key.get(
                _python_node_dependency_key(dependency)
            )
            if upstream_node is None:
                raise ExecutorInputError(
                    f"Python node '{node.name}' depends on a node outside the executor selection"
                )
            names.append(upstream_node.name)
        upstream_names[node.name] = tuple(names)
    return upstream_names


def _python_node_dependency_key(dependency: object) -> object | tuple[str, str]:
    task_definition: TaskDefinition | None = (
        get_task_definition(dependency) if callable(dependency) else None
    )
    if task_definition is not None:
        return ("name", task_definition.name)
    asset_definition: AssetDefinition | None = (
        get_asset_definition(dependency) if callable(dependency) else None
    )
    if asset_definition is not None:
        return ("name", asset_definition.name)
    return dependency


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
