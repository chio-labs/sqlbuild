"""Concurrent build scheduler using ready-queue DAG dispatch."""

from __future__ import annotations

import dataclasses
import logging
import queue
import time
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo, StatementRecorder
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
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
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.constants import (
    BUILD_CUSTOM_MATERIALIZATION_MISSING_CODE,
    BUILD_MODEL_ENTRY_MISSING_CODE,
    BUILD_SOURCE_FRESHNESS_BLOCKED_CODE,
    BUILD_UNKNOWN_RESOURCE_FAILED_CODE,
    BUILD_WORKER_FAILED_CODE,
    INCREMENTAL_ACTIONS,
)
from sqlbuild.executor.build.helpers.blocking import block_downstream
from sqlbuild.executor.build.helpers.end_audits import run_end_audits
from sqlbuild.executor.build.helpers.source_audits import run_pending_source_audits
from sqlbuild.executor.build.helpers.source_node import execute_build_source_node
from sqlbuild.executor.build.models import (
    BuildIndexes,
    FunctionExecutionResult,
    NodeCompletion,
    SeedExecutionResult,
    SourceLoadPlanEntry,
)
from sqlbuild.executor.custom.models import MaterializationResult, PrepareVersionContext
from sqlbuild.executor.functions.constants import FUNCTION_ENTRY_MISSING_CODE
from sqlbuild.executor.functions.main.execute import execute_function
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.main.execute import (
    execute_custom_entry,
    execute_incremental_entry,
    execute_microbatch_entry,
    execute_snapshot_entry,
    execute_table_entry,
    execute_view_entry,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.seed.constants import SEED_ENTRY_MISSING_CODE
from sqlbuild.executor.seed.main.execute import execute_seed
from sqlbuild.executor.shared.helpers.load_execution import (
    build_load_execution_indexes,
    skipped_load_result,
)
from sqlbuild.executor.shared.helpers.worker_completion import run_worker_with_completion
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.constants import SQL_TEST_ENTRY_MISSING_CODE
from sqlbuild.executor.testing.main.execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context, log_debug_event
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.project import SnapshotsConfig
from sqlbuild.spec.models.source import SourceEntry

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")

type _BuildWorkerResult = (
    ModelExecutionResult
    | SeedExecutionResult
    | FunctionExecutionResult
    | SqlTestExecutionResult
    | LoadExecutionResult
)


class BuildScheduler:
    """DAG-aware scheduler that dispatches nodes as their dependencies complete."""

    def __init__(
        self,
        *,
        plan: PlanOutput,
        indexes: BuildIndexes,
        adapter: BaseAdapter,
        connection_config: dict[str, object],
        connections: tuple[Any, ...],
        scheduler_connection: Any,
        promotion_mode: TablePromotionMode,
        run_id: str,
        runtime_dir: Path,
        query_change_tracking: bool,
        snapshots: SnapshotsConfig,
        allow_snapshot_schema_change: bool,
        run_audits: bool,
        run_tests: bool,
        fail_fast: bool,
        on_node_start: Callable[[str, ExecutionResourceKind], None] | None,
        on_node_complete: Callable[[object], None] | None,
        on_progress: Callable[[str], None] | None,
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
        warehouse_relations: dict[str, RelationInfo] | None = None,
        on_sub_progress: Callable[[str], None] | None = None,
        use_color: bool = False,
        precompleted_keys: frozenset[CompiledObjectKey] = frozenset(),
        initial_load_results: tuple[LoadExecutionResult, ...] = (),
        initial_failed_keys: frozenset[CompiledObjectKey] = frozenset(),
        providers: ProviderContainer | None = None,
        python_identity_recorder: PythonIdentityRecorder | None = None,
    ) -> None:
        self._plan: PlanOutput = plan
        self._indexes: BuildIndexes = indexes
        self._adapter: BaseAdapter = adapter
        self._connection_config: dict[str, object] = connection_config
        self._connections: tuple[Any, ...] = connections
        self._scheduler_connection: Any = scheduler_connection
        self._promotion_mode: TablePromotionMode = promotion_mode
        self._run_id: str = run_id
        self._runtime_dir: Path = runtime_dir
        self._query_change_tracking: bool = query_change_tracking
        self._snapshots: SnapshotsConfig = snapshots
        self._allow_snapshot_schema_change: bool = allow_snapshot_schema_change
        self._run_audits: bool = run_audits
        self._run_tests: bool = run_tests
        self._fail_fast: bool = fail_fast
        self._on_node_start: Callable[[str, ExecutionResourceKind], None] | None = on_node_start
        self._on_node_complete: Callable[[object], None] | None = on_node_complete
        self._on_progress: Callable[[str], None] | None = on_progress
        self._before_model_materialize: Callable[[ModelPlanEntry, Any], None] | None = (
            before_model_materialize
        )
        self._custom_materializations: Mapping[str, Callable[..., MaterializationResult]] = (
            custom_materializations or {}
        )
        self._custom_prepare_version_functions: Mapping[
            str, Callable[[PrepareVersionContext], None]
        ] = custom_prepare_version_functions or {}
        self._loader_functions_by_name: dict[str, DiscoveredLoaderFunction] = {
            loader.name: loader for loader in loader_functions
        }
        self._loader_ref_entries: dict[Callable[..., object], SourceEntry] = (
            build_load_execution_indexes(
                sources=tuple(plan.source_map.values()),
                loader_functions=loader_functions,
            ).loader_ref_entries
        )
        self._loader_is_reload: bool = loader_is_reload
        self._start_cursor_ts: datetime | None = start_cursor_ts
        self._end_cursor_ts: datetime | None = end_cursor_ts
        self._start_cursor_int: int | None = start_cursor_int
        self._end_cursor_int: int | None = end_cursor_int
        self._target: str = target
        self._effective_vars: dict[str, object] = effective_vars or {}
        self._warehouse_relations: dict[str, RelationInfo] = warehouse_relations or {}
        self._on_sub_progress: Callable[[str], None] | None = on_sub_progress
        self._use_color: bool = use_color
        self._providers: ProviderContainer | None = providers
        self._python_identity_recorder: PythonIdentityRecorder | None = python_identity_recorder

        self._max_concurrency: int = len(connections)
        self._blocked_keys: set[CompiledObjectKey] = set()
        self._completed_keys: set[CompiledObjectKey] = set(precompleted_keys)
        self._initial_failed_keys: frozenset[CompiledObjectKey] = initial_failed_keys
        self._in_flight: set[CompiledObjectKey] = set()
        self._ready: deque[CompiledObjectKey] = deque()
        self._stop: bool = False

        self._model_results: list[ModelExecutionResult] = []
        self._seed_results: list[SeedExecutionResult] = []
        self._function_results: list[FunctionExecutionResult] = []
        self._load_results: list[LoadExecutionResult] = list(initial_load_results)
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
            tuple(self._test_results),
            tuple(self._source_audit_results),
            end_audit_results,
        )

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
            block_downstream(
                failed_key=key,
                downstream_deps=self._plan.downstream_deps,
                selected_keys=self._plan.selected_keys,
                blocked_keys=self._blocked_keys,
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
                    result: LoadExecutionResult = self._execute_source_node(key, connection)
                    self._handle_completion(key, result)
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
                ) = self._execute_node(key, connection)
                self._handle_completion(key, result)
        finally:
            self._connection_pool.put(connection)

    def _run_concurrent(self) -> None:
        with ThreadPoolExecutor(max_workers=self._max_concurrency) as pool:
            while self._ready or self._in_flight:
                if self._stop and not self._in_flight:
                    break

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
                    if not self._pre_dispatch(key):
                        self._mark_complete(key)
                        continue
                    self._in_flight.add(key)
                    pool.submit(self._worker, key)

                if not self._in_flight:
                    break

                completion: NodeCompletion = self._completion_queue.get()
                self._in_flight.discard(completion.key)
                self._handle_completion(completion.key, completion.result)

    def _worker(self, key: CompiledObjectKey) -> None:
        run_worker_with_completion(
            key=key,
            connection_pool=self._connection_pool,
            completion_queue=self._completion_queue,
            execute=lambda connection: self._execute_node(key, connection),
            build_success=_build_worker_success_completion,
            build_failure=_build_worker_failure_completion,
        )

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
            source_blocked: bool = run_pending_source_audits(
                model_key=key,
                upstream_deps=self._plan.upstream_deps,
                downstream_deps=self._plan.downstream_deps,
                selected_keys=self._plan.selected_keys,
                source_audits_by_source=self._indexes.source_audits_by_source,
                executed_source_audits=self._executed_source_audits,
                failed_sources=self._failed_sources,
                blocked_keys=self._blocked_keys,
                adapter=self._adapter,
                connection=self._scheduler_connection,
                model_locations=self._plan.model_locations,
                seed_locations=self._plan.seed_locations,
                source_map=self._plan.source_map,
                all_source_audit_results=self._source_audit_results,
                fail_fast=self._fail_fast,
            )
            if source_blocked:
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
        self, key: CompiledObjectKey, connection: Any
    ) -> (
        ModelExecutionResult
        | SeedExecutionResult
        | FunctionExecutionResult
        | SqlTestExecutionResult
        | LoadExecutionResult
    ):
        """Execute a single node. Runs in a worker thread (or scheduler thread for serial)."""

        if key.resource_type == CompiledResourceType.SEED:
            return self._execute_seed_node(key, connection)
        if key.resource_type == CompiledResourceType.SOURCE:
            return self._execute_source_node(key, connection)
        if key.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}:
            return self._execute_function_node(key, connection)
        if key.resource_type == CompiledResourceType.SQL_TEST:
            return self._execute_test_node(key, connection)
        if key.resource_type == CompiledResourceType.MODEL:
            return self._execute_model_node(key, connection)
        return ModelExecutionResult(
            model_name=key.name,
            status=ExecutionStatus.FAILED,
            error_code=BUILD_UNKNOWN_RESOURCE_FAILED_CODE,
            error_message=f"unknown executable resource type '{key.resource_type}'",
        )

    def _execute_source_node(self, key: CompiledObjectKey, connection: Any) -> LoadExecutionResult:
        return execute_build_source_node(
            key=key,
            plan=self._plan,
            loader_functions_by_name=self._loader_functions_by_name,
            loader_ref_entries=self._loader_ref_entries,
            adapter=self._adapter,
            connection_config=self._connection_config,
            connection=connection,
            run_id=self._run_id,
            runtime_dir=self._runtime_dir,
            target=self._target,
            effective_vars=self._effective_vars,
            is_reload=self._loader_is_reload,
            start_cursor_ts=self._start_cursor_ts,
            end_cursor_ts=self._end_cursor_ts,
            start_cursor_int=self._start_cursor_int,
            end_cursor_int=self._end_cursor_int,
            on_progress=self._on_progress,
            on_node_start=self._on_node_start,
            use_color=self._use_color,
            providers=self._providers,
        )

    def _execute_seed_node(self, key: CompiledObjectKey, connection: Any) -> SeedExecutionResult:
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
            self._on_node_start(seed_entry.name, ExecutionResourceKind.SEED)
        start: float = time.monotonic()
        log_debug_event(
            _DEBUG_LOGGER,
            "",
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
            _DEBUG_LOGGER,
            "",
            sqlbuild_subject="seed",
            sqlbuild_name=seed_entry.name,
            sqlbuild_event="complete",
            sqlbuild_status=completed_result.status.lower(),
            sqlbuild_duration_ms=duration,
        )
        return completed_result

    def _execute_test_node(self, key: CompiledObjectKey, connection: Any) -> SqlTestExecutionResult:
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
            _DEBUG_LOGGER,
            "",
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
            _DEBUG_LOGGER,
            "",
            sqlbuild_subject="test",
            sqlbuild_name=test_entry.name,
            sqlbuild_event="complete",
            sqlbuild_status=result.outcome.lower(),
            sqlbuild_duration_ms=duration,
        )
        return result

    def _execute_function_node(
        self, key: CompiledObjectKey, connection: Any
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
            self._on_node_start(function_entry.name, ExecutionResourceKind(str(key.resource_type)))
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

    def _execute_model_node(self, key: CompiledObjectKey, connection: Any) -> ModelExecutionResult:
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
                _model_execution_resource_kind(model_entry.materialization_type),
            )

        model_audits: tuple[AuditPlanEntry, ...] = (
            self._indexes.model_audits_by_model.get(model_entry.name, ())
            if self._run_audits
            else ()
        )

        start: float = time.monotonic()
        log_debug_event(
            _DEBUG_LOGGER,
            "",
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
                    self._before_model_materialize(model_entry, connection)
                result: ModelExecutionResult = _dispatch_model(
                    entry=model_entry,
                    adapter=self._adapter,
                    connection=connection,
                    plan=self._plan,
                    model_audits=model_audits,
                    promotion_mode=self._promotion_mode,
                    run_id=self._run_id,
                    query_change_tracking=self._query_change_tracking,
                    snapshots=self._snapshots,
                    allow_snapshot_schema_change=self._allow_snapshot_schema_change,
                    custom_materializations=self._custom_materializations,
                    custom_prepare_version_functions=self._custom_prepare_version_functions,
                    target=self._target,
                    effective_vars=self._effective_vars,
                    warehouse_relations=self._warehouse_relations,
                    on_progress=self._on_sub_progress,
                    providers=self._providers,
                    python_identity_recorder=self._python_identity_recorder,
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
            _DEBUG_LOGGER,
            "",
            sqlbuild_subject="model",
            sqlbuild_name=model_entry.name,
            sqlbuild_event="complete",
            sqlbuild_status=completed_result.status.lower(),
            sqlbuild_duration_ms=duration,
        )
        return completed_result

    def _handle_completion(
        self,
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
                        block_downstream(
                            failed_key=dep_key,
                            downstream_deps=self._plan.downstream_deps,
                            selected_keys=self._plan.selected_keys,
                            blocked_keys=self._blocked_keys,
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
            block_downstream(
                failed_key=key,
                downstream_deps=self._plan.downstream_deps,
                selected_keys=self._plan.selected_keys,
                blocked_keys=self._blocked_keys,
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
                    skipped_load_result(self._plan.source_map[load_entry.name])
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


def _build_worker_success_completion(
    key: CompiledObjectKey, result: _BuildWorkerResult
) -> NodeCompletion:
    return NodeCompletion(key=key, result=result)


def _build_worker_failure_completion(key: CompiledObjectKey, error: Exception) -> NodeCompletion:
    return NodeCompletion(
        key=key,
        result=ModelExecutionResult(
            model_name=key.name,
            status=ExecutionStatus.FAILED,
            error_code=BUILD_WORKER_FAILED_CODE,
            error_message=str(error),
        ),
    )


def _dispatch_model(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    plan: PlanOutput,
    model_audits: tuple[AuditPlanEntry, ...],
    promotion_mode: TablePromotionMode,
    run_id: str,
    query_change_tracking: bool,
    snapshots: SnapshotsConfig,
    allow_snapshot_schema_change: bool,
    custom_materializations: Mapping[str, Callable[..., MaterializationResult]] | None = None,
    custom_prepare_version_functions: Mapping[str, Callable[[PrepareVersionContext], None]]
    | None = None,
    target: str = "",
    effective_vars: dict[str, object] | None = None,
    warehouse_relations: dict[str, RelationInfo] | None = None,
    on_progress: Callable[[str], None] | None = None,
    providers: ProviderContainer | None = None,
    python_identity_recorder: PythonIdentityRecorder | None = None,
) -> ModelExecutionResult:
    """Route a model to the correct executor based on action and mode."""

    if entry.action == PlanAction.SKIP:
        return ModelExecutionResult(
            model_name=entry.name,
            status=ExecutionStatus.SKIPPED,
            skip_reason=_plan_skip_reason(entry),
            error_code=_plan_skip_error_code(entry),
        )

    if entry.action == PlanAction.CUSTOM:
        mat_name: str | None = entry.custom_materialization_name
        registry: Mapping[str, Callable[..., MaterializationResult]] = custom_materializations or {}
        prepare_registry: Mapping[str, Callable[[PrepareVersionContext], None]] = (
            custom_prepare_version_functions or {}
        )
        if mat_name is None or mat_name not in registry:
            return ModelExecutionResult(
                model_name=entry.name,
                status=ExecutionStatus.FAILED,
                error_code=BUILD_CUSTOM_MATERIALIZATION_MISSING_CODE,
                error_message=f"custom materialization '{mat_name}' not found in registry",
            )
        existing: RelationInfo | None = (warehouse_relations or {}).get(entry.name)
        return execute_custom_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            model_audits=model_audits,
            declared_columns=entry.declared_columns,
            materialize_fn=registry[mat_name],
            prepare_version_fn=prepare_registry.get(mat_name),
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            target=target,
            effective_vars=effective_vars or {},
            existing_relation=existing,
            on_progress=on_progress,
            hook_functions=plan.hook_functions,
            effective_target_name=target,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )

    is_microbatch: bool = entry.incremental_mode == IncrementalMode.MICROBATCH
    is_full_refresh_microbatch: bool = (
        is_microbatch
        and entry.action == PlanAction.CREATE_TABLE
        and entry.materialization_type == MaterializationType.INCREMENTAL
    )

    if is_microbatch and entry.action in INCREMENTAL_ACTIONS:
        return execute_microbatch_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            model_audits=model_audits,
            declared_columns=entry.declared_columns,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            hook_functions=plan.hook_functions,
            effective_target_name=target,
            effective_vars=effective_vars,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )
    if is_full_refresh_microbatch:
        return execute_microbatch_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            model_audits=model_audits,
            declared_columns=entry.declared_columns,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            is_full_refresh=True,
            hook_functions=plan.hook_functions,
            effective_target_name=target,
            effective_vars=effective_vars,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )
    if entry.action in INCREMENTAL_ACTIONS:
        return execute_incremental_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            model_audits=model_audits,
            declared_columns=entry.declared_columns,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            hook_functions=plan.hook_functions,
            effective_target_name=target,
            effective_vars=effective_vars,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )
    if entry.action == PlanAction.CREATE_VIEW:
        return execute_view_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            model_audits=model_audits,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            hook_functions=plan.hook_functions,
            effective_target_name=target,
            effective_vars=effective_vars,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )
    if entry.action == PlanAction.SNAPSHOT:
        return execute_snapshot_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            model_audits=model_audits,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            snapshots=snapshots,
            allow_snapshot_schema_change=allow_snapshot_schema_change,
            hook_functions=plan.hook_functions,
            effective_target_name=target,
            effective_vars=effective_vars,
            providers=providers,
            python_identity_recorder=python_identity_recorder,
        )
    return execute_table_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_locations=plan.model_locations,
        seed_locations=plan.seed_locations,
        source_map=plan.source_map,
        model_audits=model_audits,
        declared_columns=entry.declared_columns,
        promotion_mode=promotion_mode,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        hook_functions=plan.hook_functions,
        effective_target_name=target,
        effective_vars=effective_vars,
        providers=providers,
        python_identity_recorder=python_identity_recorder,
    )


def _plan_skip_reason(entry: ModelPlanEntry) -> str:
    if entry.reason == PlanReason.SOURCE_FRESHNESS_ERROR:
        return "Blocked by source freshness error"
    return entry.reason.value


def _plan_skip_error_code(entry: ModelPlanEntry) -> str | None:
    if entry.reason == PlanReason.SOURCE_FRESHNESS_ERROR:
        return BUILD_SOURCE_FRESHNESS_BLOCKED_CODE
    return None


def _model_execution_resource_kind(materialization_type: str) -> ExecutionResourceKind:
    if materialization_type == MaterializationType.VIEW:
        return ExecutionResourceKind.VIEW
    if materialization_type == MaterializationType.CUSTOM:
        return ExecutionResourceKind.CUSTOM
    if materialization_type == MaterializationType.SNAPSHOT:
        return ExecutionResourceKind.SNAPSHOT
    return ExecutionResourceKind.TABLE
