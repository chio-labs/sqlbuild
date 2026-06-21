"""Executor pipeline orchestration for build execution."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.executor.build.main.execute import execute_build_plan
from sqlbuild.executor.build.main.external_source_loads import (
    run_external_source_loads_before_connections,
)
from sqlbuild.executor.build.models import BuildExecutionResult, ExternalSourceLoadResults
from sqlbuild.executor.custom.models import MaterializationResult, PrepareVersionContext
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.pipeline.helpers.auditing import (
    run_audit_pipeline as run_audit_pipeline,
)
from sqlbuild.executor.pipeline.helpers.scenario import (
    run_scenario_capture_pipeline as run_scenario_capture_pipeline,
)
from sqlbuild.executor.pipeline.helpers.scenario import (
    run_scenario_local_test_pipeline as run_scenario_local_test_pipeline,
)
from sqlbuild.executor.pipeline.helpers.scenario import (
    run_scenario_test_pipeline as run_scenario_test_pipeline,
)
from sqlbuild.executor.pipeline.helpers.scenario import (
    select_scenario_snapshot_capture_candidates as select_scenario_snapshot_capture_candidates,
)
from sqlbuild.executor.pipeline.helpers.seeding import (
    run_seed_pipeline as run_seed_pipeline,
)
from sqlbuild.executor.pipeline.helpers.settings import resolve_promotion_mode
from sqlbuild.executor.pipeline.helpers.testing import (
    run_test_pipeline as run_test_pipeline,
)
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.project import SettingsConfig, SnapshotsConfig


def run_build_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    settings: SettingsConfig,
    run_id: str,
    runtime_dir: Path = Path("target"),
    snapshots: SnapshotsConfig | None = None,
    allow_snapshot_schema_change: bool = False,
    run_tests: bool = True,
    run_audits: bool = True,
    fail_fast: bool = False,
    max_concurrency: int = 1,
    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None,
    on_node_complete: Callable[[object], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_sub_progress: Callable[[str], None] | None = None,
    before_model_materialize: Callable[[ModelPlanEntry, Any], None] | None = None,
    custom_materializations: Mapping[str, Callable[..., MaterializationResult]] | None = None,
    custom_prepare_version_functions: Mapping[str, Callable[[PrepareVersionContext], None]]
    | None = None,
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = (),
    loader_is_reload: bool = False,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    target: str = "",
    effective_vars: dict[str, object] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    use_color: bool = False,
    query_change_tracking: bool | None = None,
    precompleted_keys: frozenset[CompiledObjectKey] = frozenset(),
    initial_load_results: tuple[LoadExecutionResult, ...] = (),
    initial_failed_keys: frozenset[CompiledObjectKey] = frozenset(),
    providers: ProviderContainer | None = None,
    python_identity_recorder: PythonIdentityRecorder | None = None,
) -> BuildExecutionResult:
    """Execute a full build pipeline: resolve settings, open connections, run plan, close."""

    promotion_mode: TablePromotionMode = resolve_promotion_mode(settings=settings, adapter=adapter)
    effective_concurrency: int = max(1, max_concurrency)
    logger: logging.Logger = logging.getLogger("sqlbuild.executor.pipeline")
    external_source_load_results: ExternalSourceLoadResults = (
        run_external_source_loads_before_connections(
            plan=plan,
            loader_functions=loader_functions,
            adapter=adapter,
            connection_config=connection_config,
            run_id=run_id,
            runtime_dir=runtime_dir,
            target=target,
            effective_vars=effective_vars,
            is_reload=loader_is_reload,
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
            on_progress=on_progress,
            on_node_start=on_node_start,
            on_node_complete=on_node_complete,
            use_color=use_color,
            precompleted_keys=precompleted_keys,
            providers=providers,
        )
    )
    worker_connections: list[Any] = []
    scheduler_connection: Any | None = None
    if on_connection_start is not None:
        on_connection_start(effective_concurrency)
    start: float = time.monotonic()
    try:
        logger.debug("open scheduler connection")
        scheduler_connection = adapter.connect(connection_config)
        _i: int
        for _i in range(effective_concurrency):
            logger.debug("open worker connection index=%s", _i)
            worker_connections.append(adapter.connect(connection_config))
    except Exception:
        if on_connection_error is not None:
            on_connection_error(effective_concurrency, time.monotonic() - start)
        conn: Any
        for _i, conn in enumerate(worker_connections):
            logger.debug("close worker connection index=%s", _i)
            adapter.close(conn)
        if scheduler_connection is not None:
            logger.debug("close scheduler connection")
            adapter.close(scheduler_connection)
        raise
    if on_connection_complete is not None:
        on_connection_complete(effective_concurrency, time.monotonic() - start)
    try:
        return execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config=connection_config,
            connections=tuple(worker_connections),
            scheduler_connection=scheduler_connection,
            promotion_mode=promotion_mode,
            run_id=run_id,
            runtime_dir=runtime_dir,
            query_change_tracking=(
                settings.query_change_tracking
                if query_change_tracking is None
                else query_change_tracking
            ),
            snapshots=snapshots or SnapshotsConfig(),
            allow_snapshot_schema_change=allow_snapshot_schema_change,
            run_audits=run_audits,
            run_tests=run_tests,
            fail_fast=fail_fast,
            on_node_start=on_node_start,
            on_node_complete=on_node_complete,
            on_progress=on_progress,
            before_model_materialize=before_model_materialize,
            custom_materializations=custom_materializations,
            custom_prepare_version_functions=custom_prepare_version_functions,
            loader_functions=loader_functions,
            loader_is_reload=loader_is_reload,
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
            target=target,
            effective_vars=effective_vars,
            on_sub_progress=on_sub_progress,
            use_color=use_color,
            precompleted_keys=precompleted_keys | external_source_load_results.completed_keys,
            initial_load_results=(*initial_load_results, *external_source_load_results.results),
            initial_failed_keys=initial_failed_keys | external_source_load_results.failed_keys,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )
    finally:
        conn: Any
        for _i, conn in enumerate(worker_connections):
            logger.debug("close worker connection index=%s", _i)
            adapter.close(conn)
        logger.debug("close scheduler connection")
        if scheduler_connection is not None:
            adapter.close(scheduler_connection)
