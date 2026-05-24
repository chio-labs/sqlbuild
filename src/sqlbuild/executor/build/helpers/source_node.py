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
    environment: str,
    effective_vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    on_progress: Callable[[str], None] | None,
    on_node_start: Callable[[str, ExecutionResourceKind], None] | None,
    use_color: bool = False,
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
        environment=environment,
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
    )
    duration: int = int((time.monotonic() - start) * 1000)
    return dataclasses.replace(result, duration_ms=duration)
