"""Execution helpers for Python check nodes."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.helpers.fingerprinting import (
    try_write_python_node_identity_fingerprint,
)
from sqlbuild.executor.python_nodes.helpers.results import normalize_python_check_return
from sqlbuild.executor.python_nodes.models import (
    CheckContext,
    PythonCheckExecutionResult,
    PythonCheckResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
)
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.main.runtime import (
    ProviderContainer,
    _empty_provider_container,
    invoke_with_providers,
)
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.shared.types import PythonCheckSeverity


def execute_python_check_nodes(
    *,
    check_functions: tuple[DiscoveredCheckFunction, ...],
    python_graph: PythonNodeGraph,
    upstream_python_results: tuple[PythonNodeExecutionResult, ...],
    upstream_load_results: tuple[LoadExecutionResult, ...],
    upstream_load_results_by_loader_name: Mapping[str, LoadExecutionResult] | None = None,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    run_state: PythonNodeRunState,
    default_database: str | None = None,
    default_schema: str | None = None,
    relation_targets: dict[SqlResourceRef, str] | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    logger: logging.Logger | None = None,
    providers: ProviderContainer | None = None,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute check nodes after their selected Python dependencies have completed."""

    python_results_by_name: dict[str, PythonNodeExecutionResult] = {
        result.node_name: result for result in upstream_python_results
    }
    loader_results_by_name: dict[str, PythonNodeExecutionResult] = {
        result.source_name: _load_result_to_python_result(result)
        for result in upstream_load_results
    }
    if upstream_load_results_by_loader_name is not None:
        loader_results_by_name.update(
            {
                loader_name: _load_result_to_python_result(result, node_name=loader_name)
                for loader_name, result in upstream_load_results_by_loader_name.items()
            }
        )
    selected_check_names: frozenset[str] = frozenset(check.name for check in check_functions)
    results: list[PythonCheckExecutionResult] = []
    check_function: DiscoveredCheckFunction
    for check_function in check_functions:
        upstream_results: tuple[PythonNodeExecutionResult, ...] = tuple(
            _upstream_result(
                upstream_name=upstream_name,
                python_results_by_name=python_results_by_name,
                loader_results_by_name=loader_results_by_name,
            )
            for upstream_name in python_graph.upstream_deps.get(check_function.name, ())
            if upstream_name not in selected_check_names
        )
        blocked: PythonCheckExecutionResult | None = _blocked_check_result(
            check=check_function,
            upstream_results=upstream_results,
        )
        if blocked is not None:
            results.append(blocked)
            continue
        context: CheckContext = CheckContext(
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            run_id=run_id,
            target=target,
            vars=vars,
            is_reload=is_reload,
            logger=logger or logging.getLogger(f"sqlbuild.check.{check_function.name}"),
            statement_recorder=StatementRecorder(),
            run_state=run_state,
            default_database=default_database,
            default_schema=default_schema,
            relation_targets={} if relation_targets is None else relation_targets,
            allowed_sql_refs=frozenset(),
            providers=providers if providers is not None else _empty_provider_container(),
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
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
            results.append(
                PythonCheckExecutionResult(
                    node_name=check_function.name,
                    passed=False,
                    severity=PythonCheckSeverity.ERROR,
                    error_message=str(error),
                )
            )
            continue
        severity: PythonCheckSeverity = check_result.severity or check_function.severity
        result: PythonCheckExecutionResult = PythonCheckExecutionResult(
            node_name=check_function.name,
            passed=check_result.passed,
            severity=severity,
            message=check_result.message,
            metadata=check_result.metadata,
        )
        results.append(result)
        if not result.failed:
            try_write_python_node_identity_fingerprint(
                identity=python_graph.nodes_by_name[check_function.name].identity,
                adapter=adapter,
                connection=connection,
                run_id=run_id,
                database=default_database,
                schema=default_schema,
            )
    return tuple(results)


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
    result: LoadExecutionResult, *, node_name: str | None = None
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
