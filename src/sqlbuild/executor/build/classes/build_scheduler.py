"""Concurrent build scheduler using ready-queue DAG dispatch."""

from __future__ import annotations

import dataclasses
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, CancelledError, Future, ThreadPoolExecutor, wait
from contextvars import copy_context
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    IncrementalMode,
    IncrementalStrategy,
    PlanAction,
)
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build._helpers.blocking import downstream_blocked_keys
from sqlbuild.executor.build._helpers.end_audits import run_end_audits
from sqlbuild.executor.build._helpers.indexes import build_execution_indexes
from sqlbuild.executor.build._helpers.scheduler import (
    _build_worker_failure_completion,
    _build_worker_success_completion,
    _dispatch_model,
    _model_execution_resource_kind,
)
from sqlbuild.executor.build._helpers.source_audits import run_pending_source_audits
from sqlbuild.executor.build._helpers.source_node import execute_build_source_node
from sqlbuild.executor.build.constants import (
    BUILD_MODEL_ENTRY_MISSING_CODE,
    BUILD_UNKNOWN_RESOURCE_FAILED_CODE,
    BUILD_WORKER_FAILED_CODE,
)
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildIndexes,
    BuildInitialState,
    BuildRuntimeParams,
    FunctionExecutionResult,
    NodeCompletion,
    SeedExecutionResult,
    SourceAuditRunResult,
    SourceLoadPlanEntry,
)
from sqlbuild.executor.build.types import BeforeModelMaterializeCallback
from sqlbuild.executor.custom.models import MaterializationResult
from sqlbuild.executor.functions.constants import FUNCTION_ENTRY_MISSING_CODE
from sqlbuild.executor.functions.main._execute import execute_function
from sqlbuild.executor.load.main._build_execution_indexes import build_load_execution_indexes
from sqlbuild.executor.load.main._skipped_result import skipped_load_result
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.models import (
    BatchWindow,
    MicrobatchPhaseOutcome,
    ModelExecutionResult,
    ModelMaterializationContext,
)
from sqlbuild.executor.run.types import MicrobatchBatchExecutor
from sqlbuild.executor.scheduling.main._run_worker import run_worker_with_completion
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.seed.constants import SEED_ENTRY_MISSING_CODE
from sqlbuild.executor.seed.main._execute import execute_seed
from sqlbuild.executor.testing.constants import SQL_TEST_ENTRY_MISSING_CODE
from sqlbuild.executor.testing.main._execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.microbatches.classes.direct_store import (
    DirectMicrobatchEventStore,
    direct_microbatch_scope,
)
from sqlbuild.microbatches.models import MicrobatchScope
from sqlbuild.microbatches.types import MicrobatchEventStore
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.runtime.contracts.types import ExecutionResourceKind, NodeStartCallback
from sqlbuild.spec.contracts.models import SnapshotsConfig, SourceEntry

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


def _test_result_authored_order(*, plan: PlanOutput, result: SqlTestExecutionResult) -> int:
    entry: SqlTestPlanEntry
    for index, entry in enumerate(plan.test_entries):
        if (
            entry.source_path == result.source_path
            and entry.block_index == result.block_index
            and entry.case_index == result.case_index
        ):
            return index
    return len(plan.test_entries)


class BuildScheduler:
    """DAG-aware scheduler that dispatches nodes as their dependencies complete."""

    def __init__(
        self,
        *,
        plan: PlanOutput,
        adapter: BaseAdapter,
        connection_config: dict[str, object],
        connections: tuple[Any, ...],
        scheduler_connection: Any,
        runtime: BuildRuntimeParams,
        callbacks: BuildCallbacks,
        customizations: BuildCustomizations,
        initial_state: BuildInitialState,
    ) -> None:
        if runtime.promotion_mode is None:
            raise ExecutorInputError("build scheduler requires a resolved promotion mode")
        self._runtime: BuildRuntimeParams = runtime
        self._callbacks: BuildCallbacks = callbacks
        self._plan: PlanOutput = plan
        self._indexes: BuildIndexes = build_execution_indexes(plan)
        self._adapter: BaseAdapter = adapter
        self._connection_config: dict[str, object] = connection_config
        self._connections: tuple[Any, ...] = connections
        self._scheduler_connection: Any = scheduler_connection
        self._promotion_mode: TablePromotionMode = runtime.promotion_mode
        self._run_id: str = runtime.run_id
        self._runtime_dir: Path = runtime.runtime_dir
        self._query_change_tracking: bool = (
            True if runtime.query_change_tracking is None else runtime.query_change_tracking
        )
        self._snapshots: SnapshotsConfig = runtime.snapshots or SnapshotsConfig()
        self._allow_snapshot_schema_change: bool = runtime.allow_snapshot_schema_change
        self._run_audits: bool = runtime.run_audits
        self._run_tests: bool = runtime.run_tests
        self._fail_fast: bool = runtime.fail_fast
        self._on_node_start: NodeStartCallback | None = callbacks.on_node_start
        self._on_node_complete: Callable[[object], None] | None = callbacks.on_node_complete
        self._on_progress: Callable[[str], None] | None = callbacks.on_progress
        self._before_model_materialize: BeforeModelMaterializeCallback | None = (
            callbacks.before_model_materialize
        )
        self._custom_materializations: Mapping[str, Callable[..., MaterializationResult]] = (
            customizations.custom_materializations or {}
        )
        self._loader_functions_by_name: dict[str, DiscoveredLoaderFunction] = {
            loader.name: loader for loader in customizations.loader_functions
        }
        self._loader_ref_entries: dict[Callable[..., object], SourceEntry] = (
            build_load_execution_indexes(
                sources=tuple(plan.source_map.values()),
                loader_functions=customizations.loader_functions,
            ).loader_ref_entries
        )
        self._loader_is_reload: bool = runtime.loader_is_reload
        self._start_cursor_ts: datetime | None = runtime.start_cursor_ts
        self._end_cursor_ts: datetime | None = runtime.end_cursor_ts
        self._start_cursor_int: int | None = runtime.start_cursor_int
        self._end_cursor_int: int | None = runtime.end_cursor_int
        self._target: str = runtime.target
        self._effective_vars: dict[str, object] = runtime.effective_vars or {}
        self._warehouse_relations: dict[str, RelationInfo] = initial_state.warehouse_relations or {}
        self._on_sub_progress: Callable[[str], None] | None = callbacks.on_sub_progress
        self._use_color: bool = runtime.use_color
        self._providers: ProviderContainer | None = runtime.providers
        self._python_identity_recorder: PythonIdentityRecorder | None = (
            callbacks.python_identity_recorder
        )
        self._max_concurrency: int = len(connections)
        self._blocked_keys: set[CompiledObjectKey] = set()
        self._completed_keys: set[CompiledObjectKey] = set(initial_state.precompleted_keys)
        self._initial_failed_keys: frozenset[CompiledObjectKey] = initial_state.initial_failed_keys
        self._in_flight: set[CompiledObjectKey] = set()
        self._microbatch_coordinators: set[CompiledObjectKey] = set()
        self._microbatch_coordinator_demand: int = 0
        self._microbatch_subworkers: int = 0
        self._microbatch_coordinator_lock = threading.Lock()
        self._ready: deque[CompiledObjectKey] = deque()
        self._stop: bool = False

        self._model_results: list[ModelExecutionResult] = []
        self._seed_results: list[SeedExecutionResult] = []
        self._function_results: list[FunctionExecutionResult] = []
        self._load_results: list[LoadExecutionResult] = list(initial_state.initial_load_results)
        self._test_results: list[SqlTestExecutionResult] = []
        self._source_audit_results: list[AuditExecutionResult] = []

        self._executed_source_audits: set[str] = set()
        self._failed_sources: set[str] = set()

        self._completion_queue: queue.Queue[NodeCompletion] = queue.Queue()
        self._connection_pool: queue.Queue[Any] = queue.Queue()

        self._in_degree: dict[CompiledObjectKey, int] = {}
        self._selected_execution_keys: frozenset[CompiledObjectKey] = frozenset(
            plan.execution_order
        )

    def run(
        self,
    ) -> tuple[
        tuple[ModelExecutionResult, ...],
        tuple[SeedExecutionResult, ...],
        tuple[FunctionExecutionResult, ...],
        tuple[LoadExecutionResult, ...],
        tuple[SqlTestExecutionResult, ...],
        tuple[AuditExecutionResult, ...],
        tuple[AuditExecutionResult, ...],
    ]:
        """Execute the full build schedule and return all results."""

        self._init_connection_pool()
        self._provision_direct_microbatch_state()
        self._block_initial_failed_keys()
        self._compute_in_degrees()
        self._seed_ready_queue()

        if self._max_concurrency == 1:
            self._run_serial()
        else:
            self._run_concurrent()

        self._skip_remaining()

        end_audit_results: tuple[AuditExecutionResult, ...] = ()
        if self._run_audits and self._indexes.end_audits:
            end_audit_results = run_end_audits(
                end_audits=self._indexes.end_audits,
                adapter=self._adapter,
                connection=self._scheduler_connection,
                model_locations=self._plan.model_locations,
                seed_locations=self._plan.seed_locations,
                source_map=self._plan.source_map,
            )

        return (
            tuple(self._model_results),
            tuple(self._seed_results),
            tuple(self._function_results),
            tuple(self._load_results),
            tuple(sorted(self._test_results, key=self._test_result_order)),
            tuple(self._source_audit_results),
            end_audit_results,
        )

    def _test_result_order(self, result: SqlTestExecutionResult) -> int:
        return _test_result_authored_order(plan=self._plan, result=result)

    def _provision_direct_microbatch_state(self) -> None:
        if self._runtime.microbatch_state_resolver is not None:
            return
        locations: set[tuple[str | None, str]] = {
            (entry.destination.database, entry.destination.schema)
            for entry in self._plan.model_entries
            if entry.incremental_mode == IncrementalMode.MICROBATCH
            and entry.action != PlanAction.SKIP
            and entry.destination.schema is not None
        }
        for database, schema in sorted(
            locations, key=lambda location: (location[0] or "", location[1])
        ):
            self._adapter.execute(
                connection=self._scheduler_connection,
                sql=self._adapter.render_create_microbatch_state_table_sql(
                    database=database, schema=schema
                ),
            )
            for index_sql in self._adapter.render_create_microbatch_state_index_sqls(
                database=database, schema=schema
            ):
                self._adapter.execute(connection=self._scheduler_connection, sql=index_sql)

    def _init_connection_pool(self) -> None:
        connection: Any
        for connection in self._connections:
            self._connection_pool.put(connection)

    def _compute_in_degrees(self) -> None:
        key: CompiledObjectKey
        for key in self._selected_execution_keys:
            if key in self._completed_keys:
                continue
            upstream: tuple[CompiledObjectKey, ...] = self._plan.upstream_deps.get(key, ())
            count: int = 0
            dep: CompiledObjectKey
            for dep in upstream:
                if dep in self._selected_execution_keys and dep not in self._completed_keys:
                    count += 1
            self._in_degree[key] = count

    def _seed_ready_queue(self) -> None:
        key: CompiledObjectKey
        for key in self._plan.execution_order:
            if key in self._completed_keys:
                continue
            if self._in_degree.get(key, 0) == 0:
                self._ready.append(key)

    def _block_initial_failed_keys(self) -> None:
        key: CompiledObjectKey
        for key in self._initial_failed_keys:
            self._blocked_keys.update(
                downstream_blocked_keys(
                    failed_key=key,
                    downstream_deps=self._plan.downstream_deps,
                    selected_keys=self._plan.selected_keys,
                )
            )
        if self._fail_fast and self._initial_failed_keys:
            self._stop = True

    def _run_serial(self) -> None:
        connection: Any = self._connection_pool.get()
        try:
            while self._ready:
                if self._stop:
                    break
                key: CompiledObjectKey = self._ready.popleft()
                if key.resource_type == CompiledResourceType.SOURCE:
                    if not self._pre_dispatch(key):
                        self._mark_complete(key)
                        continue
                    result: LoadExecutionResult = cast(
                        LoadExecutionResult,
                        self._execute_node(key=key, connection=connection),
                    )
                    self._handle_completion(key=key, result=result)
                    continue
                if key in self._blocked_keys:
                    self._record_skipped(key)
                    self._mark_complete(key)
                    continue
                if not self._pre_dispatch(key):
                    self._mark_complete(key)
                    continue
                result: (
                    ModelExecutionResult
                    | SeedExecutionResult
                    | FunctionExecutionResult
                    | SqlTestExecutionResult
                    | LoadExecutionResult
                ) = self._execute_node(key=key, connection=connection)
                self._handle_completion(key=key, result=result)
        finally:
            self._connection_pool.put(connection)

    def _run_concurrent(self) -> None:
        with ThreadPoolExecutor(max_workers=self._max_concurrency) as pool:
            while self._ready or self._in_flight:
                if self._stop and not self._in_flight:
                    break

                with self._microbatch_coordinator_lock:
                    queued_coordinators: int = sum(
                        1 for key in tuple(self._ready) if self._is_concurrent_microbatch(key)
                    )
                    self._microbatch_coordinator_demand = min(
                        self._max_concurrency,
                        len(self._microbatch_coordinators) + queued_coordinators,
                    )

                while self._ready and len(self._in_flight) < self._max_concurrency:
                    if self._stop:
                        break
                    key: CompiledObjectKey = self._ready.popleft()
                    if key.resource_type == CompiledResourceType.SOURCE:
                        if not self._pre_dispatch(key):
                            self._mark_complete(key)
                            continue
                        self._in_flight.add(key)
                        pool.submit(self._worker, key)
                        continue
                    if key in self._blocked_keys:
                        self._record_skipped(key)
                        self._mark_complete(key)
                        continue
                    if self._is_concurrent_microbatch(key) and any(
                        not self._is_concurrent_microbatch(candidate) for candidate in self._ready
                    ):
                        self._ready.append(key)
                        continue
                    if not self._pre_dispatch(key):
                        self._mark_complete(key)
                        continue
                    if self._is_concurrent_microbatch(key):
                        with self._microbatch_coordinator_lock:
                            if (
                                len(self._microbatch_coordinators) + self._microbatch_subworkers
                                >= self._max_concurrency
                            ):
                                self._ready.appendleft(key)
                                break
                            self._microbatch_coordinators.add(key)
                        self._in_flight.add(key)
                        pool.submit(self._concurrent_microbatch_worker, key=key, pool=pool)
                        continue
                    self._in_flight.add(key)
                    pool.submit(self._worker, key)

                if not self._in_flight:
                    break

                completion: NodeCompletion = self._completion_queue.get()
                self._in_flight.discard(completion.key)
                self._handle_completion(key=completion.key, result=completion.result)

    def _worker(self, key: CompiledObjectKey) -> None:
        run_worker_with_completion(
            key=key,
            connection_pool=self._connection_pool,
            completion_queue=self._completion_queue,
            execute=lambda connection: self._execute_node(key=key, connection=connection),
            build_success=_build_worker_success_completion,
            build_failure=_build_worker_failure_completion,
        )

    def _is_concurrent_microbatch(self, key: CompiledObjectKey) -> bool:
        if key.resource_type != CompiledResourceType.MODEL:
            return False
        entry: ModelPlanEntry | None = self._indexes.model_entries_by_key.get(key)
        return bool(
            self._runtime.microbatch_concurrency
            and entry is not None
            and entry.incremental_mode == IncrementalMode.MICROBATCH
            and entry.incremental_strategy == IncrementalStrategy.DELETE_INSERT
            and entry.batch_concurrency > 1
            and entry.action != PlanAction.CREATE_TABLE
        )

    def _concurrent_microbatch_worker(
        self, *, key: CompiledObjectKey, pool: ThreadPoolExecutor
    ) -> None:
        run_worker_with_completion(
            key=key,
            connection_pool=self._connection_pool,
            completion_queue=self._completion_queue,
            execute=lambda connection: self._execute_concurrent_microbatch_node(
                key=key, pool=pool, connection=connection
            ),
            build_success=_build_worker_success_completion,
            build_failure=_build_worker_failure_completion,
        )

    def _execute_concurrent_microbatch_node(
        self, *, key: CompiledObjectKey, pool: ThreadPoolExecutor, connection: Any
    ) -> ModelExecutionResult:
        try:
            with CostContext.scope(
                run_id=self._run_id,
                resource_type=str(key.resource_type),
                resource_name=key.name,
                ledger_path=(self._runtime_dir / "runs" / self._run_id / "statements.jsonl"),
            ):
                return self._execute_model_node(
                    key=key,
                    connection=connection,
                    microbatch_batch_runner=lambda batches, concurrency, execute: (
                        self._run_microbatch_subwork(
                            pool=pool,
                            coordinator_connection=connection,
                            batches=batches,
                            concurrency=concurrency,
                            execute=execute,
                        )
                    ),
                )
        finally:
            with self._microbatch_coordinator_lock:
                self._microbatch_coordinators.discard(key)

    def _run_microbatch_subwork(
        self,
        *,
        pool: ThreadPoolExecutor,
        coordinator_connection: Any,
        batches: tuple[BatchWindow, ...],
        concurrency: int,
        execute: MicrobatchBatchExecutor,
    ) -> tuple[MicrobatchPhaseOutcome, ...]:
        if not batches:
            return ()
        model_subworker_limit: int = max(0, concurrency - 1)
        if model_subworker_limit == 0:
            return tuple(execute(batch, coordinator_connection) for batch in batches)
        results: dict[int, MicrobatchPhaseOutcome] = {}
        pending_batches: deque[BatchWindow] = deque(batches)
        in_flight: dict[Future[MicrobatchPhaseOutcome], BatchWindow] = {}

        def submit_one() -> tuple[Future[MicrobatchPhaseOutcome], BatchWindow]:
            batch: BatchWindow = pending_batches.popleft()
            try:
                future: Future[MicrobatchPhaseOutcome] = cast(
                    Future[MicrobatchPhaseOutcome],
                    pool.submit(
                        copy_context().run,
                        self._run_microbatch_batch_worker,
                        batch=batch,
                        execute=execute,
                    ),
                )
            except BaseException:
                self._release_microbatch_subworker()
                raise
            return future, batch

        submitted_future: Future[MicrobatchPhaseOutcome]
        submitted_batch: BatchWindow
        while (
            len(pending_batches) > 1
            and len(in_flight) < model_subworker_limit
            and self._reserve_microbatch_subworker()
        ):
            submitted_future, submitted_batch = submit_one()
            in_flight[submitted_future] = submitted_batch
        coordinator_batch: BatchWindow = pending_batches.popleft()
        coordinator_result: MicrobatchPhaseOutcome = execute(
            coordinator_batch, coordinator_connection
        )
        results[coordinator_batch.index] = coordinator_result
        failed: bool = coordinator_result.failure is not None
        if failed:
            for future in in_flight:
                self._cancel_microbatch_subworker(future=future)
        first_exception: BaseException | None = None
        while in_flight:
            completed, _ = wait(tuple(in_flight), return_when=FIRST_COMPLETED)
            for future in completed:
                batch: BatchWindow = in_flight.pop(future)
                try:
                    outcome: MicrobatchPhaseOutcome = future.result()
                except CancelledError:
                    continue
                except BaseException as exc:
                    if first_exception is None:
                        first_exception = exc
                    failed = True
                    for sibling in in_flight:
                        self._cancel_microbatch_subworker(future=sibling)
                    continue
                results[batch.index] = outcome
                if outcome.failure is not None:
                    failed = True
                    for sibling in in_flight:
                        self._cancel_microbatch_subworker(future=sibling)
            while (
                not failed
                and pending_batches
                and len(in_flight) < model_subworker_limit
                and self._reserve_microbatch_subworker()
            ):
                submitted_future, submitted_batch = submit_one()
                in_flight[submitted_future] = submitted_batch
        if first_exception is not None:
            raise first_exception
        while not failed and pending_batches:
            batch = pending_batches.popleft()
            outcome: MicrobatchPhaseOutcome = execute(batch, coordinator_connection)
            results[batch.index] = outcome
            failed = outcome.failure is not None
        return tuple(results[index] for index in sorted(results))

    def _run_microbatch_batch_worker(
        self,
        *,
        batch: BatchWindow,
        execute: MicrobatchBatchExecutor,
    ) -> MicrobatchPhaseOutcome:
        connection: Any = self._connection_pool.get()
        try:
            return execute(batch, connection)
        finally:
            self._connection_pool.put(connection)
            self._release_microbatch_subworker()

    def _reserve_microbatch_subworker(self) -> bool:
        with self._microbatch_coordinator_lock:
            if (
                max(
                    len(self._microbatch_coordinators),
                    self._microbatch_coordinator_demand,
                )
                + self._microbatch_subworkers
                >= self._max_concurrency
            ):
                return False
            self._microbatch_subworkers += 1
            return True

    def _release_microbatch_subworker(self) -> None:
        with self._microbatch_coordinator_lock:
            self._microbatch_subworkers -= 1

    def _cancel_microbatch_subworker(self, *, future: Future[MicrobatchPhaseOutcome]) -> None:
        if not future.cancelled() and future.cancel():
            self._release_microbatch_subworker()

    def _pre_dispatch(self, key: CompiledObjectKey) -> bool:
        """Run pre-dispatch checks. Returns False if the node should be skipped."""

        if key.resource_type == CompiledResourceType.SQL_TEST:
            if not self._run_tests:
                return False
            return True

        if key.resource_type == CompiledResourceType.SOURCE:
            return key in self._indexes.source_load_entries_by_key

        if key.resource_type == CompiledResourceType.MODEL:
            if not self._run_audits:
                return True
            model_entry: ModelPlanEntry | None = self._indexes.model_entries_by_key.get(key)
            if model_entry is None:
                return False
            audit_run: SourceAuditRunResult = run_pending_source_audits(
                model_key=key,
                plan=self._plan,
                source_audits_by_source=self._indexes.source_audits_by_source,
                executed_source_audits=frozenset(self._executed_source_audits),
                failed_sources=frozenset(self._failed_sources),
                adapter=self._adapter,
                connection=self._scheduler_connection,
                fail_fast=self._fail_fast,
            )
            self._executed_source_audits.update(audit_run.executed_source_names)
            self._failed_sources.update(audit_run.failed_source_names)
            self._blocked_keys.update(audit_run.newly_blocked_keys)
            self._source_audit_results.extend(audit_run.audit_results)
            if audit_run.blocked:
                self._blocked_keys.add(key)
                self._model_results.append(
                    ModelExecutionResult(
                        model_name=model_entry.name, status=ExecutionStatus.SKIPPED
                    )
                )
                if self._fail_fast:
                    self._stop = True
                return False

        return True

    def _execute_node(
        self, *, key: CompiledObjectKey, connection: Any
    ) -> (
        ModelExecutionResult
        | SeedExecutionResult
        | FunctionExecutionResult
        | SqlTestExecutionResult
        | LoadExecutionResult
    ):
        with CostContext.scope(
            run_id=self._run_id,
            resource_type=str(key.resource_type),
            resource_name=key.name,
            ledger_path=(self._runtime_dir / "runs" / self._run_id / "statements.jsonl"),
        ):
            return self._execute_node_with_cost_context(key=key, connection=connection)

    def _execute_node_with_cost_context(
        self, *, key: CompiledObjectKey, connection: Any
    ) -> (
        ModelExecutionResult
        | SeedExecutionResult
        | FunctionExecutionResult
        | SqlTestExecutionResult
        | LoadExecutionResult
    ):
        """Execute a single node. Runs in a worker thread (or scheduler thread for serial)."""

        if key.resource_type == CompiledResourceType.SEED:
            return self._execute_seed_node(key=key, connection=connection)
        if key.resource_type == CompiledResourceType.SOURCE:
            return self._execute_source_node(key=key, connection=connection)
        if key.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}:
            return self._execute_function_node(key=key, connection=connection)
        if key.resource_type == CompiledResourceType.SQL_TEST:
            return self._execute_test_node(key=key, connection=connection)
        if key.resource_type == CompiledResourceType.MODEL:
            return self._execute_model_node(key=key, connection=connection)
        return ModelExecutionResult(
            model_name=key.name,
            status=ExecutionStatus.FAILED,
            error_code=BUILD_UNKNOWN_RESOURCE_FAILED_CODE,
            error_message=f"unknown executable resource type '{key.resource_type}'",
        )

    def _execute_source_node(
        self, *, key: CompiledObjectKey, connection: Any
    ) -> LoadExecutionResult:
        return execute_build_source_node(
            key=key,
            plan=self._plan,
            loader_functions_by_name=self._loader_functions_by_name,
            loader_ref_entries=self._loader_ref_entries,
            adapter=self._adapter,
            connection_config=self._connection_config,
            connection=connection,
            runtime=self._runtime,
            callbacks=self._callbacks,
        )

    def _execute_seed_node(self, *, key: CompiledObjectKey, connection: Any) -> SeedExecutionResult:
        seed_entry: SeedPlanEntry | None = self._indexes.seed_entries_by_key.get(key)
        if seed_entry is None:
            return SeedExecutionResult(
                seed_name=key.name,
                status=ExecutionStatus.FAILED,
                error_code=SEED_ENTRY_MISSING_CODE,
                error_message="seed entry not found",
            )
        if self._on_progress is not None:
            self._on_progress(f"seed: {seed_entry.name}")
        if self._on_node_start is not None:
            self._on_node_start(seed_entry.name, resource_kind=ExecutionResourceKind.SEED)
        start: float = time.monotonic()
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="",
            sqlbuild_subject="seed",
            sqlbuild_name=seed_entry.name,
            sqlbuild_event="start",
            sqlbuild_kind="seed",
        )
        with diagnostics_context(
            sqlbuild_subject="seed",
            sqlbuild_name=seed_entry.name,
            sqlbuild_phase="load",
            sqlbuild_kind="seed",
        ):
            result: SeedExecutionResult = execute_seed(
                seed_entry=seed_entry,
                adapter=self._adapter,
                connection=connection,
                statement_recorder=StatementRecorder(),
                run_id=self._run_id,
                query_change_tracking=self._query_change_tracking,
            )
        duration: int = int((time.monotonic() - start) * 1000)
        completed_result: SeedExecutionResult = dataclasses.replace(result, duration_ms=duration)
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="",
            sqlbuild_subject="seed",
            sqlbuild_name=seed_entry.name,
            sqlbuild_event="complete",
            sqlbuild_status=completed_result.status.lower(),
            sqlbuild_duration_ms=duration,
        )
        return completed_result

    def _execute_test_node(
        self, *, key: CompiledObjectKey, connection: Any
    ) -> SqlTestExecutionResult:
        test_entry: SqlTestPlanEntry | None = self._indexes.test_entries_by_key.get(key)
        if test_entry is None:
            return SqlTestExecutionResult(
                test_name=key.name,
                outcome=SqlTestOutcome.ERROR,
                error_code=SQL_TEST_ENTRY_MISSING_CODE,
                error_message="test entry not found",
            )
        if self._on_progress is not None:
            self._on_progress(f"test: {test_entry.name}")
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="",
            sqlbuild_subject="test",
            sqlbuild_name=test_entry.name,
            sqlbuild_event="start",
        )
        start: float = time.monotonic()
        with diagnostics_context(
            sqlbuild_subject="test",
            sqlbuild_name=test_entry.name,
            sqlbuild_phase="run",
        ):
            result: SqlTestExecutionResult = execute_sql_test(
                test_entry=test_entry, adapter=self._adapter, connection=connection
            )
        duration: int = int((time.monotonic() - start) * 1000)
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="",
            sqlbuild_subject="test",
            sqlbuild_name=test_entry.name,
            sqlbuild_event="complete",
            sqlbuild_status=result.outcome.lower(),
            sqlbuild_duration_ms=duration,
        )
        return result

    def _execute_function_node(
        self, *, key: CompiledObjectKey, connection: Any
    ) -> FunctionExecutionResult:
        function_entry: FunctionPlanEntry | None = self._indexes.function_entries_by_key.get(key)
        if function_entry is None:
            return FunctionExecutionResult(
                function_name=key.name,
                status=ExecutionStatus.FAILED,
                function_kind=str(key.resource_type),
                error_code=FUNCTION_ENTRY_MISSING_CODE,
                error_message="function entry not found",
            )
        if self._on_progress is not None:
            self._on_progress(f"{str(key.resource_type)}: {function_entry.name}")
        if self._on_node_start is not None:
            self._on_node_start(
                function_entry.name,
                resource_kind=ExecutionResourceKind(str(key.resource_type)),
            )
        start: float = time.monotonic()
        result: FunctionExecutionResult = execute_function(
            function_entry=function_entry,
            adapter=self._adapter,
            connection=connection,
            statement_recorder=StatementRecorder(),
            run_id=self._run_id,
            query_change_tracking=self._query_change_tracking,
        )
        duration: int = int((time.monotonic() - start) * 1000)
        return dataclasses.replace(result, duration_ms=duration)

    def _execute_model_node(
        self,
        *,
        key: CompiledObjectKey,
        connection: Any,
        microbatch_batch_runner: Callable[
            [
                tuple[BatchWindow, ...],
                int,
                Callable[[BatchWindow, Any], MicrobatchPhaseOutcome],
            ],
            tuple[MicrobatchPhaseOutcome, ...],
        ]
        | None = None,
    ) -> ModelExecutionResult:
        model_entry: ModelPlanEntry | None = self._indexes.model_entries_by_key.get(key)
        if model_entry is None:
            return ModelExecutionResult(
                model_name=key.name,
                status=ExecutionStatus.FAILED,
                error_code=BUILD_MODEL_ENTRY_MISSING_CODE,
                error_message="model entry not found",
            )
        if self._on_progress is not None:
            self._on_progress(f"model: {model_entry.name}")
        if self._on_node_start is not None:
            self._on_node_start(
                model_entry.name,
                resource_kind=_model_execution_resource_kind(model_entry.materialization_type),
            )

        model_audits: tuple[AuditPlanEntry, ...] = (
            self._indexes.model_audits_by_model.get(model_entry.name, ())
            if self._run_audits
            else ()
        )
        microbatch_event_store: MicrobatchEventStore | None = None
        microbatch_event_store_resolver: Callable[[Any], MicrobatchEventStore] | None = None
        microbatch_scope: MicrobatchScope | None = None

        start: float = time.monotonic()
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="",
            sqlbuild_subject="model",
            sqlbuild_name=model_entry.name,
            sqlbuild_event="start",
            sqlbuild_kind=model_entry.materialization_type,
        )
        with diagnostics_context(
            sqlbuild_subject="model",
            sqlbuild_name=model_entry.name,
            sqlbuild_kind=model_entry.materialization_type,
        ):
            try:
                if self._before_model_materialize is not None:
                    self._before_model_materialize(entry=model_entry, connection=connection)
                if model_entry.incremental_mode == IncrementalMode.MICROBATCH:
                    if self._runtime.microbatch_state_resolver is not None:
                        microbatch_event_store, microbatch_scope = (
                            self._runtime.microbatch_state_resolver(model_entry, connection)
                        )
                    else:
                        microbatch_event_store = DirectMicrobatchEventStore(
                            adapter=self._adapter, connection=connection
                        )
                        microbatch_scope = direct_microbatch_scope(
                            adapter=self._adapter,
                            connection=connection,
                            entry=model_entry,
                        )
                    microbatch_event_store_resolver = partial(
                        lambda connection, *, entry: self._microbatch_store_for_connection(
                            connection=connection, model_entry=entry
                        ),
                        entry=model_entry,
                    )
                result: ModelExecutionResult = _dispatch_model(
                    context=ModelMaterializationContext(
                        entry=model_entry,
                        adapter=self._adapter,
                        connection=connection,
                        model_locations=self._plan.model_locations,
                        seed_locations=self._plan.seed_locations,
                        source_map=self._plan.source_map,
                        model_audits=model_audits,
                        run_id=self._run_id,
                        query_change_tracking=self._query_change_tracking,
                        hook_functions=self._plan.hook_functions,
                        effective_target_name=self._target,
                        effective_vars=self._effective_vars,
                        providers=self._providers,
                        python_identity_recorder=self._python_identity_recorder,
                        microbatch_event_store=microbatch_event_store,
                        microbatch_event_store_resolver=microbatch_event_store_resolver,
                        microbatch_scope=microbatch_scope,
                        microbatch_model_version_hash=(
                            None
                            if microbatch_scope is None
                            else microbatch_scope.virtual_model_version_hash
                        ),
                        microbatch_unaccounted_partition_policy=(
                            model_entry.unaccounted_partition_policy
                            or self._runtime.microbatch_unaccounted_partition_policy
                        ),
                        microbatch_lease_check=self._runtime.microbatch_lease_check,
                        microbatch_global_concurrency=self._max_concurrency,
                        microbatch_batch_runner=microbatch_batch_runner,
                    ),
                    promotion_mode=self._promotion_mode,
                    snapshots=self._snapshots,
                    allow_snapshot_schema_change=self._allow_snapshot_schema_change,
                    custom_materializations=self._custom_materializations,
                    target=self._target,
                    effective_vars=self._effective_vars,
                    warehouse_relations=self._warehouse_relations,
                    on_progress=self._on_sub_progress,
                )
            except Exception as error:
                result = ModelExecutionResult(
                    model_name=model_entry.name,
                    status=ExecutionStatus.FAILED,
                    error_code=BUILD_WORKER_FAILED_CODE,
                    error_message=str(error),
                )
        duration: int = int((time.monotonic() - start) * 1000)
        completed_result: ModelExecutionResult = dataclasses.replace(result, duration_ms=duration)
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="",
            sqlbuild_subject="model",
            sqlbuild_name=model_entry.name,
            sqlbuild_event="complete",
            sqlbuild_status=completed_result.status.lower(),
            sqlbuild_duration_ms=duration,
        )
        return completed_result

    def _microbatch_store_for_connection(
        self, *, connection: Any, model_entry: ModelPlanEntry
    ) -> MicrobatchEventStore:
        resolver: (
            Callable[[ModelPlanEntry, object], tuple[MicrobatchEventStore, MicrobatchScope]] | None
        ) = self._runtime.microbatch_state_resolver
        if resolver is not None:
            return resolver(model_entry, connection)[0]
        return DirectMicrobatchEventStore(adapter=self._adapter, connection=connection)

    def _handle_completion(
        self,
        *,
        key: CompiledObjectKey,
        result: (
            ModelExecutionResult
            | SeedExecutionResult
            | FunctionExecutionResult
            | SqlTestExecutionResult
            | LoadExecutionResult
        ),
    ) -> None:
        """Process a completed node: record result, propagate blocking, enqueue ready."""

        failed: bool = False

        if isinstance(result, SeedExecutionResult):
            self._seed_results.append(result)
            if self._on_node_complete is not None:
                self._on_node_complete(result)
            failed = result.status == ExecutionStatus.FAILED

        elif isinstance(result, SqlTestExecutionResult):
            self._test_results.append(result)
            if self._on_node_complete is not None:
                self._on_node_complete(result)
            if result.outcome != SqlTestOutcome.PASS:
                failed = True
                test_entry: SqlTestPlanEntry | None = self._indexes.test_entries_by_key.get(key)
                if test_entry is not None:
                    dep_key: CompiledObjectKey
                    for dep_key in test_entry.scope_deps:
                        self._blocked_keys.add(dep_key)
                        self._blocked_keys.update(
                            downstream_blocked_keys(
                                failed_key=dep_key,
                                downstream_deps=self._plan.downstream_deps,
                                selected_keys=self._plan.selected_keys,
                            )
                        )

        elif isinstance(result, FunctionExecutionResult):
            self._function_results.append(result)
            if self._on_node_complete is not None:
                self._on_node_complete(result)
            failed = result.status == ExecutionStatus.FAILED

        elif isinstance(result, LoadExecutionResult):
            self._load_results.append(result)
            if self._on_node_complete is not None:
                self._on_node_complete(result)
            failed = result.status == ExecutionStatus.FAILED

        elif isinstance(result, ModelExecutionResult):
            self._model_results.append(result)
            if self._on_node_complete is not None:
                self._on_node_complete(result)
            failed = result.status in {ExecutionStatus.FAILED, ExecutionStatus.SKIPPED}

        if failed:
            self._blocked_keys.update(
                downstream_blocked_keys(
                    failed_key=key,
                    downstream_deps=self._plan.downstream_deps,
                    selected_keys=self._plan.selected_keys,
                )
            )
            if self._fail_fast:
                self._stop = True
        self._mark_complete(key)

    def _mark_complete(self, key: CompiledObjectKey) -> None:
        """Mark a key complete and enqueue any downstream that become ready."""

        self._completed_keys.add(key)
        downstream: tuple[CompiledObjectKey, ...] = self._plan.downstream_deps.get(key, ())
        neighbor: CompiledObjectKey
        for neighbor in downstream:
            if neighbor not in self._selected_execution_keys:
                continue
            if neighbor in self._completed_keys:
                continue
            self._in_degree[neighbor] = self._in_degree.get(neighbor, 1) - 1
            if self._in_degree[neighbor] <= 0:
                self._ready.append(neighbor)

    def _record_skipped(self, key: CompiledObjectKey) -> None:
        if key.resource_type == CompiledResourceType.MODEL:
            entry: ModelPlanEntry | None = self._indexes.model_entries_by_key.get(key)
            if entry is not None:
                self._model_results.append(
                    ModelExecutionResult(model_name=entry.name, status=ExecutionStatus.SKIPPED)
                )
        elif key.resource_type == CompiledResourceType.SEED:
            seed_entry: SeedPlanEntry | None = self._indexes.seed_entries_by_key.get(key)
            if seed_entry is not None:
                self._seed_results.append(
                    SeedExecutionResult(seed_name=seed_entry.name, status=ExecutionStatus.SKIPPED)
                )
        elif key.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}:
            function_entry: FunctionPlanEntry | None = self._indexes.function_entries_by_key.get(
                key
            )
            if function_entry is not None:
                self._function_results.append(
                    FunctionExecutionResult(
                        function_name=function_entry.name,
                        status=ExecutionStatus.SKIPPED,
                        function_kind=str(key.resource_type),
                    )
                )
        elif key.resource_type == CompiledResourceType.SOURCE:
            load_entry: SourceLoadPlanEntry | None = self._indexes.source_load_entries_by_key.get(
                key
            )
            if load_entry is not None:
                self._load_results.append(
                    skipped_load_result(source=self._plan.source_map[load_entry.name])
                )

    def _skip_remaining(self) -> None:
        """Skip all nodes that were never dispatched."""

        key: CompiledObjectKey
        for key in self._plan.execution_order:
            if key in self._completed_keys:
                continue
            if key in self._in_flight:
                continue
            self._record_skipped(key)
