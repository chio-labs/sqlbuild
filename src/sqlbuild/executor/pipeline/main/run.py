"""Executor pipeline orchestration for build execution."""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.executor.build.main._execute import execute_build_plan
from sqlbuild.executor.build.main._external_source_loads import (
    run_external_source_loads_before_connections,
)
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildExecutionResult,
    BuildInitialState,
    BuildRuntimeParams,
    ExternalSourceLoadResults,
)
from sqlbuild.executor.pipeline._helpers.auditing import (
    run_audit_pipeline as run_audit_pipeline,
)
from sqlbuild.executor.pipeline._helpers.connections import (
    close_connections,
    open_worker_connections,
)
from sqlbuild.executor.pipeline._helpers.graph_width import runnable_graph_width
from sqlbuild.executor.pipeline._helpers.scenario import (
    run_scenario_capture_pipeline as run_scenario_capture_pipeline,
)
from sqlbuild.executor.pipeline._helpers.scenario import (
    run_scenario_local_test_pipeline as run_scenario_local_test_pipeline,
)
from sqlbuild.executor.pipeline._helpers.scenario import (
    run_scenario_test_pipeline as run_scenario_test_pipeline,
)
from sqlbuild.executor.pipeline._helpers.scenario import (
    select_scenario_snapshot_capture_candidates as select_scenario_snapshot_capture_candidates,
)
from sqlbuild.executor.pipeline._helpers.seeding import (
    run_seed_pipeline as run_seed_pipeline,
)
from sqlbuild.executor.pipeline._helpers.settings import resolve_build_inputs
from sqlbuild.executor.pipeline._helpers.testing import (
    run_test_pipeline as run_test_pipeline,
)
from sqlbuild.executor.pipeline.models import ResolvedBuildInputs
from sqlbuild.spec.contracts.models import SettingsConfig, SourceEntry


def run_build_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    settings: SettingsConfig,
    runtime: BuildRuntimeParams,
    callbacks: BuildCallbacks | None = None,
    customizations: BuildCustomizations | None = None,
    initial_state: BuildInitialState | None = None,
) -> BuildExecutionResult:
    """Execute a full build pipeline: resolve settings, open connections, run plan, close."""

    with CostContext.scope(
        run_id=runtime.run_id,
        resource_type="run",
        resource_name=runtime.target,
        ledger_path=runtime.runtime_dir / "runs" / runtime.run_id / "statements.jsonl",
        phase="build",
    ):
        return _run_build_pipeline(
            plan=plan,
            connection_config=connection_config,
            adapter=adapter,
            settings=settings,
            runtime=runtime,
            callbacks=callbacks,
            customizations=customizations,
            initial_state=initial_state,
        )


def _run_build_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    settings: SettingsConfig,
    runtime: BuildRuntimeParams,
    callbacks: BuildCallbacks | None = None,
    customizations: BuildCustomizations | None = None,
    initial_state: BuildInitialState | None = None,
) -> BuildExecutionResult:
    """Run the build while the public wrapper owns telemetry context."""

    inputs: ResolvedBuildInputs = resolve_build_inputs(
        settings=settings,
        adapter=adapter,
        runtime=runtime,
        callbacks=callbacks,
        customizations=customizations,
        initial_state=initial_state,
    )
    effective_concurrency: int = min(
        max(1, runtime.max_concurrency), runnable_graph_width(plan=plan)
    )
    logger: logging.Logger = logging.getLogger("sqlbuild.executor.pipeline")
    external_source_load_results: ExternalSourceLoadResults = (
        run_external_source_loads_before_connections(
            plan=plan,
            loader_functions=inputs.customizations.loader_functions,
            adapter=adapter,
            connection_config=connection_config,
            runtime=inputs.runtime,
            callbacks=inputs.callbacks,
            precompleted_keys=inputs.initial_state.precompleted_keys,
        )
    )
    merged_initial_state: BuildInitialState = replace(
        inputs.initial_state,
        precompleted_keys=inputs.initial_state.precompleted_keys
        | external_source_load_results.completed_keys,
        initial_load_results=(
            *inputs.initial_state.initial_load_results,
            *external_source_load_results.results,
        ),
        initial_failed_keys=inputs.initial_state.initial_failed_keys
        | external_source_load_results.failed_keys,
    )
    worker_connections: list[Any] = []
    scheduler_connection: Any | None = None
    physical_connection_count: int = effective_concurrency + 1
    if inputs.callbacks.on_connection_start is not None:
        inputs.callbacks.on_connection_start(physical_connection_count)
    start: float = time.monotonic()
    try:
        logger.debug("open scheduler connection")
        scheduler_connection = adapter.connect(connection_config)
        _ = _prepare_build_schemas(
            plan=plan,
            adapter=adapter,
            connection_config=connection_config,
            connection=scheduler_connection,
        )
        worker_connections = list(
            open_worker_connections(
                adapter=adapter,
                connection_config=connection_config,
                connection_count=effective_concurrency,
            )
        )
    except BaseException as error:
        if inputs.callbacks.on_connection_error is not None:
            inputs.callbacks.on_connection_error(
                physical_connection_count, elapsed_seconds=time.monotonic() - start
            )
        cleanup_connections: tuple[Any, ...] = tuple(worker_connections) + (
            () if scheduler_connection is None else (scheduler_connection,)
        )
        _ = close_connections(
            adapter=adapter,
            connections=cleanup_connections,
            active_error=error,
        )
        raise
    if inputs.callbacks.on_connection_complete is not None:
        inputs.callbacks.on_connection_complete(
            physical_connection_count, elapsed_seconds=time.monotonic() - start
        )
    execution_error: BaseException | None = None
    try:
        return execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config=connection_config,
            connections=tuple(worker_connections),
            scheduler_connection=scheduler_connection,
            runtime=inputs.runtime,
            callbacks=inputs.callbacks,
            customizations=inputs.customizations,
            initial_state=merged_initial_state,
        )
    except BaseException as error:
        execution_error = error
        raise
    finally:
        cleanup_connections: tuple[Any, ...] = tuple(worker_connections) + (
            () if scheduler_connection is None else (scheduler_connection,)
        )
        _ = close_connections(
            adapter=adapter,
            connections=cleanup_connections,
            active_error=execution_error,
        )


def _prepare_build_schemas(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any | None = None,
) -> None:
    schemas: set[tuple[str | None, str]] = set()
    for entry in (*plan.model_entries, *plan.seed_entries, *plan.function_entries):
        if entry.destination.schema is not None:
            schemas.add((entry.destination.database, entry.destination.schema))
    for entry in plan.source_load_entries:
        source_entry: SourceEntry | None = plan.source_map.get(entry.name)
        if source_entry is not None and source_entry.schema is not None:
            schemas.add((source_entry.database, source_entry.schema))
    if not schemas:
        return

    owned_connection: bool = connection is None
    schema_connection: Any = (
        connection if connection is not None else adapter.connect(connection_config)
    )
    recorder: StatementRecorder = StatementRecorder()
    try:
        for database, schema in sorted(schemas, key=lambda item: (item[0] or "", item[1])):
            adapter.ensure_schema(
                connection=schema_connection,
                database=database,
                schema=schema,
                statement_recorder=recorder,
            )
    finally:
        if owned_connection:
            adapter.close(schema_connection)
