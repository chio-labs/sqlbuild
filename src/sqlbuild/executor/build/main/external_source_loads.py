"""Public entrypoint for pre-connection external source-load execution."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.helpers.external_source_loads import (
    run_external_source_loads_before_connections as _run_external_source_loads_before_connections,
)
from sqlbuild.executor.build.models import ExternalSourceLoadResults
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExecutionResourceKind


def run_external_source_loads_before_connections(
    *,
    plan: PlanOutput,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    run_id: str,
    target: str,
    effective_vars: dict[str, object] | None,
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    on_progress: Callable[[str], None] | None,
    on_node_start: Callable[[str, ExecutionResourceKind], None] | None,
    on_node_complete: Callable[[object], None] | None,
    use_color: bool,
    providers: ProviderContainer | None = None,
) -> ExternalSourceLoadResults:
    """Run external source-load nodes before SQLBuild opens warehouse connections."""

    return _run_external_source_loads_before_connections(
        plan=plan,
        loader_functions=loader_functions,
        adapter=adapter,
        connection_config=connection_config,
        run_id=run_id,
        target=target,
        effective_vars=effective_vars,
        is_reload=is_reload,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        on_progress=on_progress,
        on_node_start=on_node_start,
        on_node_complete=on_node_complete,
        use_color=use_color,
        providers=providers,
    )
