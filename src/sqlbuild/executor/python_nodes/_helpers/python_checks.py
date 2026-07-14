"""Execution helpers for Python check nodes."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonNodeIdentity
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.exceptions import ExecutorInputError
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.node_results.main.standard_store import build_standard_node_result_store
from sqlbuild.executor.node_results.models import NodeResultRecord
from sqlbuild.executor.node_results.types import NodeResultStatus
from sqlbuild.executor.python_nodes._helpers.fingerprinting import (
    try_write_python_node_identity_fingerprint,
)
from sqlbuild.executor.python_nodes._helpers.results import normalize_python_check_return
from sqlbuild.executor.python_nodes.models import (
    CheckContext,
    PythonCheckExecutionResult,
    PythonCheckResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.types import ExecutionStatus
from sqlbuild.provider.main.runtime import (
    ProviderContainer,
    _empty_provider_container,
    invoke_with_providers,
)
from sqlbuild.python_nodes.types import PythonCheckSeverity


def execute_python_check_nodes(
    *,
    check_functions: tuple[DiscoveredCheckFunction, ...],
    python_graph: PythonNodeGraph,
    upstream_python_results: tuple[PythonNodeExecutionResult, ...],
    upstream_load_results: tuple[LoadExecutionResult, ...],
    runtime: PythonNodeRuntime,
    run_state: PythonNodeRunState,
    upstream_load_results_by_loader_name: Mapping[str, LoadExecutionResult] | None = None,
    logger: logging.Logger | None = None,
    identity_recorder: PythonIdentityRecorder | None = None,
    require_upstream_results: bool = True,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute check nodes after their selected Python dependencies have completed."""

    adapter: BaseAdapter = runtime.adapter
    connection: Any = runtime.connection
    run_id: str = runtime.run_id
    default_database: str | None = runtime.default_database
    default_schema: str | None = runtime.default_schema
    providers: ProviderContainer | None = runtime.providers
    python_results_by_name: dict[str, PythonNodeExecutionResult] = {
        result.node_name: result for result in upstream_python_results
    }
    loader_results_by_name: dict[str, PythonNodeExecutionResult] = {
        result.source_name: _load_result_to_python_result(result=result)
        for result in upstream_load_results
    }
    if upstream_load_results_by_loader_name is not None:
        loader_results_by_name.update(
            {
                loader_name: _load_result_to_python_result(result=result, node_name=loader_name)
                for loader_name, result in upstream_load_results_by_loader_name.items()
            }
        )
    selected_check_names: frozenset[str] = frozenset(check.name for check in check_functions)
    resolved_result_store: Any | None = (
        runtime.result_store
        if runtime.result_store is not None
        else (
            build_standard_node_result_store(
                adapter=adapter,
                connection=connection,
                database=default_database,
                schema=default_schema,
            )
            if runtime.persist_node_results
            else None
        )
    )
    results: list[PythonCheckExecutionResult] = []
    check_function: DiscoveredCheckFunction
    for check_function in check_functions:
        upstream_results: tuple[PythonNodeExecutionResult, ...] = _check_upstream_results(
            upstream_names=python_graph.upstream_deps.get(check_function.name, ()),
            selected_check_names=selected_check_names,
            python_results_by_name=python_results_by_name,
            loader_results_by_name=loader_results_by_name,
            require_upstream_results=require_upstream_results,
        )
        blocked: PythonCheckExecutionResult | None = _blocked_check_result(
            check=check_function,
            upstream_results=upstream_results,
        )
        if blocked is not None:
            _persist_check_result(
                result_store=resolved_result_store,
                result=blocked,
                run_id=run_id,
            )
            results.append(blocked)
            continue
        context: CheckContext = CheckContext(
            adapter=adapter,
            connection_config=runtime.connection_config,
            connection=connection,
            run_id=run_id,
            target=runtime.target,
            vars=runtime.vars,
            is_reload=runtime.is_reload,
            logger=logger or logging.getLogger(f"sqlbuild.check.{check_function.name}"),
            statement_recorder=StatementRecorder(),
            run_state=run_state,
            result_store=resolved_result_store,
            default_database=default_database,
            default_schema=default_schema,
            relation_targets=runtime.resolved_relation_targets,
            allowed_sql_refs=frozenset(),
            providers=providers if providers is not None else _empty_provider_container(),
            start_cursor_ts=runtime.start_cursor_ts,
            end_cursor_ts=runtime.end_cursor_ts,
            start_cursor_int=runtime.start_cursor_int,
            end_cursor_int=runtime.end_cursor_int,
        )
        try:
            returned: object = invoke_with_providers(
                function=check_function.function,
                context=context,
                providers=providers,
            )
            check_result: PythonCheckResult = normalize_python_check_return(
                returned=returned,
                default_severity=check_function.severity,
            )
        except Exception as error:
            error_result: PythonCheckExecutionResult = PythonCheckExecutionResult(
                node_name=check_function.name,
                passed=False,
                severity=PythonCheckSeverity.ERROR,
                error_message=str(error),
            )
            _persist_check_result(
                result_store=resolved_result_store,
                result=error_result,
                run_id=run_id,
            )
            results.append(error_result)
            continue
        severity: PythonCheckSeverity = check_result.severity or check_function.severity
        result: PythonCheckExecutionResult = PythonCheckExecutionResult(
            node_name=check_function.name,
            passed=check_result.passed,
            severity=severity,
            message=check_result.message,
            metadata=check_result.metadata,
        )
        _persist_check_result(
            result_store=resolved_result_store,
            result=result,
            run_id=run_id,
        )
        results.append(result)
        if not result.failed:
            identity: PythonNodeIdentity | None = python_graph.nodes_by_name[
                check_function.name
            ].identity
            if identity_recorder is not None:
                identity_recorder(identity=identity, _target_name=None)
            else:
                try_write_python_node_identity_fingerprint(
                    identity=identity,
                    adapter=adapter,
                    connection=connection,
                    run_id=run_id,
                    database=default_database,
                    schema=default_schema,
                )
    return tuple(results)


def _persist_check_result(
    *, result_store: Any | None, result: PythonCheckExecutionResult, run_id: str
) -> None:
    if result_store is None:
        return
    status: NodeResultStatus = (
        NodeResultStatus.SUCCESS
        if result.passed
        else NodeResultStatus.WARN
        if result.warned
        else NodeResultStatus.FAILED
    )
    result_store.write(
        NodeResultRecord(
            node_type=PythonNodeKind.CHECK.value,
            node_name=result.node_name,
            target_database=result_store.database,
            target_schema=result_store.schema,
            target_name=None,
            run_id=run_id,
            status=status.value,
            payload=None,
            metadata=result.metadata,
            error_message=result.error_message or result.message,
            materialized=None,
        )
    )


def _upstream_result(
    *,
    upstream_name: str,
    python_results_by_name: Mapping[str, PythonNodeExecutionResult],
    loader_results_by_name: Mapping[str, PythonNodeExecutionResult],
) -> PythonNodeExecutionResult:
    result: PythonNodeExecutionResult | None = python_results_by_name.get(
        upstream_name
    ) or loader_results_by_name.get(upstream_name)
    if result is None:
        raise ExecutorInputError(
            f"Python check dependency '{upstream_name}' did not run before check execution"
        )
    return result


def _check_upstream_results(
    *,
    upstream_names: tuple[str, ...],
    selected_check_names: frozenset[str],
    python_results_by_name: Mapping[str, PythonNodeExecutionResult],
    loader_results_by_name: Mapping[str, PythonNodeExecutionResult],
    require_upstream_results: bool,
) -> tuple[PythonNodeExecutionResult, ...]:
    results: list[PythonNodeExecutionResult] = []
    upstream_name: str
    for upstream_name in upstream_names:
        if upstream_name in selected_check_names:
            continue
        if require_upstream_results:
            results.append(
                _upstream_result(
                    upstream_name=upstream_name,
                    python_results_by_name=python_results_by_name,
                    loader_results_by_name=loader_results_by_name,
                )
            )
            continue
        result: PythonNodeExecutionResult | None = python_results_by_name.get(
            upstream_name
        ) or loader_results_by_name.get(upstream_name)
        if result is not None:
            results.append(result)
    return tuple(results)


def _blocked_check_result(
    *, check: DiscoveredCheckFunction, upstream_results: tuple[PythonNodeExecutionResult, ...]
) -> PythonCheckExecutionResult | None:
    failed_names: tuple[str, ...] = tuple(
        result.node_name for result in upstream_results if result.status == PythonNodeStatus.FAILED
    )
    if failed_names:
        return PythonCheckExecutionResult(
            node_name=check.name,
            passed=False,
            severity=PythonCheckSeverity.ERROR,
            error_message=f"Upstream Python node failed: {', '.join(failed_names)}",
        )
    skipped_names: tuple[str, ...] = tuple(
        result.node_name for result in upstream_results if result.status == PythonNodeStatus.SKIPPED
    )
    if skipped_names:
        return PythonCheckExecutionResult(
            node_name=check.name,
            passed=False,
            severity=PythonCheckSeverity.WARN,
            message=f"Upstream Python node skipped: {', '.join(skipped_names)}",
        )
    return None


def _load_result_to_python_result(
    *, result: LoadExecutionResult, node_name: str | None = None
) -> PythonNodeExecutionResult:
    status: PythonNodeStatus = (
        PythonNodeStatus.SUCCESS
        if result.status == ExecutionStatus.SUCCESS
        else PythonNodeStatus.SKIPPED
        if result.status == ExecutionStatus.SKIPPED
        else PythonNodeStatus.FAILED
    )
    return PythonNodeExecutionResult(
        node_name=result.source_name if node_name is None else node_name,
        kind=PythonNodeKind.LOADER,
        status=status,
        payload=result,
        error_message=result.error_message,
    )
