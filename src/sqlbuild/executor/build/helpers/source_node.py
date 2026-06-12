"""Build-scheduler adapter for executable source-load nodes."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import PlanOutput, SourceLoadPlanEntry
from sqlbuild.executor.load.main.execute import execute_source_load
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.node_results.classes.standard_store import StandardNodeResultStore
from sqlbuild.executor.node_results.main.standard_store import build_standard_node_result_store
from sqlbuild.executor.node_results.models import NodeResultRecord
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry


def execute_build_source_node(
    *,
    key: CompiledObjectKey,
    plan: PlanOutput,
    loader_functions_by_name: dict[str, DiscoveredLoaderFunction],
    loader_ref_entries: dict[Callable[..., object], SourceEntry],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str,
    effective_vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    on_progress: Callable[[str], None] | None,
    on_node_start: Callable[[str, ExecutionResourceKind], None] | None,
    use_color: bool = False,
    providers: ProviderContainer | None = None,
) -> LoadExecutionResult:
    """Execute one source-load node from the build scheduler."""

    source_entry: SourceEntry = plan.source_map[key.name]
    source_load_entry: SourceLoadPlanEntry | None = next(
        (entry for entry in plan.source_load_entries if entry.key == key), None
    )
    resource_kind: ExecutionResourceKind = (
        source_load_entry.resource_kind
        if source_load_entry is not None
        else ExecutionResourceKind.SOURCE
    )
    loader_name: str = source_entry.loader or ""
    loader_function: DiscoveredLoaderFunction = loader_functions_by_name[loader_name]
    if on_progress is not None:
        on_progress(f"source: {source_entry.name}")
    if on_node_start is not None:
        on_node_start(source_entry.name, resource_kind)
    start: float = time.monotonic()
    result: LoadExecutionResult = execute_source_load(
        source_entry=source_entry,
        loader_function=loader_function,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=effective_vars,
        is_reload=is_reload,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        statement_recorder=StatementRecorder(),
        use_color=use_color,
        loader_ref_entries=loader_ref_entries,
        source_ref_entries=plan.source_map,
        providers=providers,
    )
    duration: int = int((time.monotonic() - start) * 1000)
    timed_result: LoadExecutionResult = dataclasses.replace(result, duration_ms=duration)
    _persist_loader_result(
        adapter=adapter,
        connection=connection,
        loader_name=loader_name,
        result=timed_result,
        run_id=run_id,
    )
    return timed_result


def _persist_loader_result(
    *,
    adapter: BaseAdapter,
    connection: Any,
    loader_name: str,
    result: LoadExecutionResult,
    run_id: str,
) -> None:
    result_store: StandardNodeResultStore = build_standard_node_result_store(
        adapter=adapter,
        connection=connection,
        database=adapter.default_database(),
        schema=adapter.default_schema(),
    )
    result_store.write(
        NodeResultRecord(
            node_type="loader",
            node_name=loader_name,
            target_database=result_store.database,
            target_schema=result_store.schema,
            target_name=None,
            run_id=run_id,
            status=result.status.value,
            payload={
                "source_name": result.source_name,
                "loader_name": result.loader_name,
                "rows_loaded": result.rows_loaded,
                "target": result.target,
            },
            metadata={},
            error_message=result.error_message or result.skip_reason,
            materialized=None,
        )
    )
