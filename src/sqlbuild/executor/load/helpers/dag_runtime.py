"""Concurrent DAG helpers for source loader execution."""

from __future__ import annotations

import queue
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.load.main.execute import execute_source_load
from sqlbuild.executor.load.models import LoadDagState, LoadExecutionIndexes, LoadExecutionResult
from sqlbuild.executor.shared.helpers.load_execution import (
    load_resource_kind,
    should_skip_due_to_hard_dependency,
    should_soft_skip_due_to_all_skipped_dependencies,
    skipped_load_result,
)
from sqlbuild.executor.shared.helpers.python_node_scheduler import (
    build_python_node_in_degree,
    build_python_node_ready_queue,
    unlock_downstream_python_nodes,
)
from sqlbuild.executor.shared.helpers.worker_completion import run_worker_with_completion
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry


def build_load_dag_state(
    *,
    sources: tuple[SourceEntry, ...],
    results: list[LoadExecutionResult | None],
    source_index_by_name: dict[str, int],
    upstream_names: dict[str, tuple[str, ...]],
    downstream_names: dict[str, tuple[str, ...]],
) -> LoadDagState:
    """Build mutable state for concurrent source-loader DAG execution."""

    source_names: tuple[str, ...] = tuple(source.name for source in sources)
    in_degree: dict[str, int] = build_python_node_in_degree(
        node_names=source_names,
        upstream_names=upstream_names,
    )
    ready: list[str] = build_python_node_ready_queue(
        node_names=source_names,
        in_degree=in_degree,
    )
    return LoadDagState(
        results=results,
        in_degree=in_degree,
        ready=ready,
        in_flight=set(),
        failed_or_skipped=set(),
        results_by_name={},
        source_index_by_name=source_index_by_name,
        downstream_names=downstream_names,
        completion_queue=queue.Queue(),
    )


def complete_dag_source(
    *,
    source_name: str,
    result: LoadExecutionResult,
    state: LoadDagState,
    on_load_complete: Callable[[LoadExecutionResult], None] | None,
) -> None:
    """Record one completed source-loader node and unlock downstream nodes."""

    source_index: int = state.source_index_by_name[source_name]
    state.results[source_index] = result
    state.results_by_name[source_name] = result
    if result.status == ExecutionStatus.FAILED or (
        result.status == ExecutionStatus.SKIPPED and result.skip_mode == SkipMode.HARD
    ):
        state.failed_or_skipped.add(source_name)
    if on_load_complete is not None:
        on_load_complete(result)
    unlock_downstream_python_nodes(
        completed_node_name=source_name,
        in_degree=state.in_degree,
        ready=state.ready,
        downstream_names=state.downstream_names,
    )


def execute_ready_dag_source(
    *,
    source_name: str,
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    failed_or_hard_skipped: set[str],
    results_by_name: dict[str, LoadExecutionResult] | None = None,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    runtime_dir: Path = Path("target"),
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    use_color: bool = False,
    on_progress: Callable[[str], None] | None = None,
    providers: ProviderContainer | None = None,
    result_store: Any | None = None,
) -> LoadExecutionResult:
    """Execute one ready DAG node or return a skipped result."""

    source: SourceEntry = source_by_name[source_name]
    if should_skip_due_to_hard_dependency(
        source=source,
        failed_or_hard_skipped=failed_or_hard_skipped,
        indexes=indexes,
    ):
        return skipped_load_result(source, reason="Upstream loader hard-skipped")
    if should_soft_skip_due_to_all_skipped_dependencies(
        source=source,
        results_by_name={} if results_by_name is None else results_by_name,
        indexes=indexes,
    ):
        return skipped_load_result(
            source,
            reason="All upstream loaders were soft-skipped",
            mode=SkipMode.SOFT,
        )
    return execute_source_load(
        source_entry=source,
        loader_function=indexes.loader_by_name[source.loader or ""],
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        runtime_dir=runtime_dir,
        target=target,
        vars=vars,
        is_reload=is_reload,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        statement_recorder=StatementRecorder(),
        use_color=use_color,
        loader_ref_entries=indexes.loader_ref_entries,
        source_ref_entries=indexes.source_by_name,
        on_progress=on_progress,
        providers=providers,
        result_store=result_store,
    )


def load_dag_worker(
    source_name: str,
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    failed_or_hard_skipped: set[str],
    results_by_name: dict[str, LoadExecutionResult],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection_pool: queue.Queue[Any],
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    use_color: bool,
    completion_queue: queue.Queue[tuple[str, LoadExecutionResult]],
    on_load_progress: Callable[[SourceEntry, str], None] | None = None,
    providers: ProviderContainer | None = None,
    result_store: Any | None = None,
    runtime_dir: Path = Path("target"),
) -> None:
    """Worker wrapper for concurrent DAG source-loader execution."""

    def _execute(connection: Any) -> LoadExecutionResult:
        return execute_ready_dag_source(
            source_name=source_name,
            source_by_name=source_by_name,
            indexes=indexes,
            failed_or_hard_skipped=failed_or_hard_skipped,
            results_by_name=results_by_name,
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            run_id=run_id,
            runtime_dir=runtime_dir,
            target=target,
            vars=vars,
            is_reload=is_reload,
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
            use_color=use_color,
            on_progress=(
                None
                if on_load_progress is None
                else lambda message: on_load_progress(source_by_name[source_name], message)
            ),
            providers=providers,
            result_store=result_store,
        )

    run_worker_with_completion(
        key=source_name,
        connection_pool=connection_pool,
        completion_queue=completion_queue,
        execute=_execute,
        build_success=_load_dag_success_completion,
        build_failure=lambda failed_source_name, error: _load_dag_failure_completion(
            source_name=failed_source_name,
            source_by_name=source_by_name,
            error=error,
        ),
    )


def _load_dag_success_completion(
    source_name: str, result: LoadExecutionResult
) -> tuple[str, LoadExecutionResult]:
    return (source_name, result)


def _load_dag_failure_completion(
    *, source_name: str, source_by_name: dict[str, SourceEntry], error: Exception
) -> tuple[str, LoadExecutionResult]:
    source: SourceEntry | None = source_by_name.get(source_name)
    loader_name: str = (source.loader or "") if source is not None else ""
    target: str = (source.table or source.name) if source is not None else source_name
    resource_kind: ExecutionResourceKind = (
        load_resource_kind(source) if source is not None else ExecutionResourceKind.SOURCE
    )
    return (
        source_name,
        LoadExecutionResult(
            source_name=source.name if source is not None else source_name,
            loader_name=loader_name,
            status=ExecutionStatus.FAILED,
            target=target,
            resource_kind=resource_kind,
            error_message=str(error),
        ),
    )
