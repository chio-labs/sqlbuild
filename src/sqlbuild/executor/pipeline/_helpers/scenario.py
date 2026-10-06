"""Scenario test execution pipeline."""

from __future__ import annotations

import logging
import queue
import sys
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import copy_context
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, ClassVar, Protocol, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.compiler.compile.models import CompiledSqlScenario
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main.scenarios.scenario import build_scenario_plan
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.errors.contracts.main.error_code import error_code
from sqlbuild.errors.contracts.main.error_help import error_help
from sqlbuild.errors.contracts.main.error_message import error_message
from sqlbuild.executor.pipeline._helpers.connections import (
    close_connections,
    open_worker_connections,
)
from sqlbuild.executor.pipeline._helpers.settings import resolve_promotion_mode
from sqlbuild.executor.scenario.classes.prepared_scenario_schemas import PreparedScenarioSchemas
from sqlbuild.executor.scenario.constants import (
    SCENARIO_EXEC_INTERNAL,
    SCENARIO_LOCAL_INTERNAL,
)
from sqlbuild.executor.scenario.main._capture_steps import (
    execute_scenario_snapshot_capture_run,
)
from sqlbuild.executor.scenario.main._local import execute_local_scenario_load_only_run
from sqlbuild.executor.scenario.main._run import execute_scenario_run
from sqlbuild.executor.scenario.main._snapshots import classify_scenario_snapshot_state
from sqlbuild.executor.scenario.models import (
    ScenarioCaptureSettings,
    ScenarioLocalReplaySource,
    ScenarioRunOptions,
    ScenarioRunResult,
    ScenarioSnapshotCaptureRunResult,
    ScenarioSnapshotStateResult,
)
from sqlbuild.executor.scenario.types import ScenarioLocalRunStatus, ScenarioSnapshotState
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.presentation.main.transient_line_coordinator import (
    shared_transient_line_coordinator,
)
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)
from sqlbuild.spec.contracts.main.scenario_local_type_overrides_for_dialect import (
    scenario_local_type_overrides_for_dialect,
)

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")
_INTERRUPT_NOTICE: str = "Interrupted; cleaning up running scenarios...\n"
_STOP_POLL_SECONDS: float = 0.05
_SCENARIO_INTERNAL_ERROR_HELP: str = (
    "This is likely a SQLBuild bug. Please file an issue with the scenario name."
)


@dataclass(frozen=True)
class _ScenarioScheduling:
    worker_count: int = 1
    stop_requested: threading.Event = field(default_factory=threading.Event)


@dataclass(frozen=True)
class _ScenarioOutcome[ResultT]:
    scenario: CompiledSqlScenario
    scenario_plan: ScenarioExecutionPlan | None
    result: ResultT
    resource_attempt_id: str


def _scenario_failure_help(exc: Exception) -> str | None:
    explicit_help: str | None = error_help(exc)
    if explicit_help is not None:
        return explicit_help
    if getattr(exc, "code", None) is not None:
        return None
    return _SCENARIO_INTERNAL_ERROR_HELP


class _ScenarioPipelineResult(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Any]]

    @property
    def status(self) -> ExecutionStatus: ...

    @property
    def error_code(self) -> str | None: ...


class _ScenarioFailureResult[ResultT](Protocol):
    def __call__(self, *, scenario_name: str, exc: Exception) -> ResultT: ...


def run_scenario_test_pipeline(
    *,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    project_name: str,
    retain: bool,
    concurrency: int = 1,
    connection_hooks: ConnectionHooks | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioRunResult, ...]:
    """Execute selected scenarios from a compiled project."""

    worker_count: int = max(1, min(concurrency, len(scenarios)))
    with _scenario_target_connections(
        adapter=adapter,
        connection_config=connection_config,
        connection_hooks=connection_hooks,
        connection_count=worker_count,
    ) as connection_pool:
        stop_requested: threading.Event = threading.Event()
        options: ScenarioRunOptions = ScenarioRunOptions(
            promotion_mode=resolve_promotion_mode(
                settings=pipeline_result.project.settings, adapter=adapter
            ),
            prepared_schemas=PreparedScenarioSchemas(),
            stop_requested=stop_requested,
        )

        def execute(scenario_plan: ScenarioExecutionPlan) -> ScenarioRunResult:
            connection: Any = connection_pool.get()
            try:
                return execute_scenario_run(
                    scenario_plan=scenario_plan,
                    adapter=adapter,
                    connection=connection,
                    run_id=pipeline_result.project.run_id,
                    retain=retain,
                    options=options,
                )
            finally:
                connection_pool.put(connection)

        def failed(*, scenario_name: str, exc: Exception) -> ScenarioRunResult:
            return ScenarioRunResult(
                scenario_name=scenario_name,
                status=ExecutionStatus.FAILED,
                retained=retain,
                error_code=error_code(error=exc, fallback_code=SCENARIO_EXEC_INTERNAL),
                error_help=_scenario_failure_help(exc),
                error_message=error_message(exc),
            )

        return _run_scenarios(
            pipeline_result=pipeline_result,
            scenarios=scenarios,
            adapter=adapter,
            project_name=project_name,
            source_lexical_syntax=adapter.sql_lexical_syntax,
            execute=execute,
            failed=failed,
            on_scenario_start=on_scenario_start,
            on_scenario_complete=on_scenario_complete,
            scheduling=_ScenarioScheduling(
                worker_count=worker_count, stop_requested=stop_requested
            ),
        )


def run_scenario_local_test_pipeline(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    strict: bool,
    replay_source: ScenarioLocalReplaySource,
    concurrency: int = 1,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioRunResult, ...]:
    """Load selected local scenario snapshots into run-scoped DuckDB databases."""

    promotion_mode: TablePromotionMode = resolve_promotion_mode(
        settings=pipeline_result.project.settings, adapter=adapter
    )

    def execute(scenario_plan: ScenarioExecutionPlan) -> ScenarioRunResult:
        return execute_local_scenario_load_only_run(
            project_dir=project_dir,
            scenario_plan=scenario_plan,
            adapter=adapter,
            strict=strict,
            promotion_mode=promotion_mode,
            capture_adapter=replay_source.capture_adapter,
            capture_dialect=replay_source.capture_dialect,
        )

    def failed(*, scenario_name: str, exc: Exception) -> ScenarioRunResult:
        return ScenarioRunResult(
            scenario_name=scenario_name,
            status=ExecutionStatus.FAILED,
            local_status=ScenarioLocalRunStatus.ERROR,
            retained=False,
            error_code=error_code(error=exc, fallback_code=SCENARIO_LOCAL_INTERNAL),
            error_help=_scenario_failure_help(exc),
            error_message=error_message(exc),
        )

    return _run_scenarios(
        pipeline_result=pipeline_result,
        scenarios=scenarios,
        adapter=adapter,
        project_name=project_name,
        source_lexical_syntax=replay_source.lexical_syntax,
        execute=execute,
        failed=failed,
        on_scenario_start=on_scenario_start,
        on_scenario_complete=on_scenario_complete,
        scheduling=_ScenarioScheduling(worker_count=max(1, min(concurrency, len(scenarios)))),
    )


def run_scenario_capture_pipeline(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    project_name: str,
    settings: ScenarioCaptureSettings,
    connection_hooks: ConnectionHooks | None = None,
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None = None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ScenarioSnapshotCaptureRunResult], None
    ]
    | None = None,
) -> tuple[ScenarioSnapshotCaptureRunResult, ...]:
    """Capture selected scenario inputs into durable local snapshot files."""

    with _scenario_target_connections(
        adapter=adapter,
        connection_config=connection_config,
        connection_hooks=connection_hooks,
        connection_count=1,
    ) as connection_pool:
        connection: Any = connection_pool.get()

        def execute(scenario_plan: ScenarioExecutionPlan) -> ScenarioSnapshotCaptureRunResult:
            return execute_scenario_snapshot_capture_run(
                project_dir=project_dir,
                scenario_plan=scenario_plan,
                adapter=adapter,
                connection=connection,
                run_id=pipeline_result.project.run_id,
                settings=settings,
                local_type_overrides=scenario_local_type_overrides_for_dialect(
                    scenario_config=pipeline_result.project.scenario,
                    sql_analysis_dialect=adapter.sql_analysis_dialect(),
                ),
            )

        def failed(*, scenario_name: str, exc: Exception) -> ScenarioSnapshotCaptureRunResult:
            return ScenarioSnapshotCaptureRunResult(
                scenario_name=scenario_name,
                status=ExecutionStatus.FAILED,
                retained=settings.retain,
                error_code=error_code(error=exc, fallback_code=SCENARIO_EXEC_INTERNAL),
                error_help=_scenario_failure_help(exc),
                error_message=error_message(exc),
            )

        return _run_scenarios(
            pipeline_result=pipeline_result,
            scenarios=scenarios,
            adapter=adapter,
            project_name=project_name,
            source_lexical_syntax=adapter.sql_lexical_syntax,
            execute=execute,
            failed=failed,
            on_scenario_start=on_scenario_start,
            on_scenario_complete=on_scenario_complete,
        )


@contextmanager
def _scenario_target_connections(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection_hooks: ConnectionHooks | None,
    connection_count: int,
) -> Iterator[queue.SimpleQueue[Any]]:
    hooks: ConnectionHooks = connection_hooks if connection_hooks is not None else ConnectionHooks()
    if hooks.on_connection_start is not None:
        hooks.on_connection_start(connection_count)
    start: float = time.monotonic()
    try:
        with OperationLifecycle(
            operation_kind="scenario", operation_name="scenario_target_connection"
        ):
            connections: tuple[Any, ...] = open_worker_connections(
                adapter=adapter,
                connection_config=connection_config,
                connection_count=connection_count,
            )
    except Exception:
        if hooks.on_connection_error is not None:
            hooks.on_connection_error(connection_count, elapsed_seconds=time.monotonic() - start)
        raise
    if hooks.on_connection_complete is not None:
        hooks.on_connection_complete(connection_count, elapsed_seconds=time.monotonic() - start)
    connection_pool: queue.SimpleQueue[Any] = queue.SimpleQueue()
    connection: Any
    for connection in connections:
        connection_pool.put(connection)
    active_error: BaseException | None = None
    try:
        yield connection_pool
    except BaseException as error:
        active_error = error
        raise
    finally:
        close_connections(adapter=adapter, connections=connections, active_error=active_error)


def _run_scenarios[ResultT: _ScenarioPipelineResult](
    *,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    source_lexical_syntax: SqlLexicalSyntax,
    execute: Callable[[ScenarioExecutionPlan], ResultT],
    failed: _ScenarioFailureResult[ResultT],
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None,
    on_scenario_complete: Callable[
        [CompiledSqlScenario, ScenarioExecutionPlan | None, ResultT], None
    ]
    | None,
    scheduling: _ScenarioScheduling | None = None,
) -> tuple[ResultT, ...]:
    resolved_scheduling: _ScenarioScheduling = (
        scheduling if scheduling is not None else _ScenarioScheduling()
    )

    def run(*, scenario: CompiledSqlScenario, notify_start: bool) -> _ScenarioOutcome[ResultT]:
        return _run_scenario(
            scenario=scenario,
            pipeline_result=pipeline_result,
            adapter=adapter,
            project_name=project_name,
            source_lexical_syntax=source_lexical_syntax,
            execute=execute,
            failed=failed,
            on_scenario_start=on_scenario_start if notify_start else None,
        )

    def complete(outcome: _ScenarioOutcome[ResultT]) -> ResultT:
        projector: NativeProgressProjector | None = current_native_progress_projector()
        if projector is not None and on_scenario_complete is not None:
            _ = projector.consume_resource_terminal(
                resource_name=outcome.scenario.name,
                resource_id=_scenario_resource_id(outcome.scenario.name),
                resource_attempt_id=outcome.resource_attempt_id,
            )
        if on_scenario_complete is not None:
            on_scenario_complete(outcome.scenario, outcome.scenario_plan, outcome.result)
        return outcome.result

    scenario: CompiledSqlScenario
    for scenario in scenarios:
        _prepare_scenario_presentation(
            scenario_name=scenario.name,
            has_completion_callback=on_scenario_complete is not None,
        )
    results: list[ResultT] = []
    with ThreadPoolExecutor(max_workers=max(1, resolved_scheduling.worker_count)) as pool:
        futures: tuple[Future[_ScenarioOutcome[ResultT]], ...] = tuple(
            cast(
                Future[_ScenarioOutcome[ResultT]],
                pool.submit(copy_context().run, run, scenario=scenario, notify_start=False),
            )
            for scenario in scenarios
        )
        try:
            index: int
            future: Future[_ScenarioOutcome[ResultT]]
            for index, future in enumerate(futures):
                if on_scenario_start is not None:
                    on_scenario_start(scenarios[index])
                results.append(complete(future.result()))
        except BaseException as error:
            _stop_scenarios(
                error=error,
                futures=futures,
                stop_requested=resolved_scheduling.stop_requested,
            )
            raise
    return tuple(results)


def _stop_scenarios[OutcomeT](
    *,
    error: BaseException,
    futures: tuple[Future[OutcomeT], ...],
    stop_requested: threading.Event,
) -> None:
    """Cancel queued scenarios and await running ones' cleanup, absorbing repeat interrupts."""

    if not isinstance(error, Exception):
        shared_transient_line_coordinator().write_persistent(
            stream=sys.stderr, text=_INTERRUPT_NOTICE
        )
    stop_requested.set()
    future: Future[OutcomeT]
    for future in futures:
        _ = future.cancel()
    pending: tuple[Future[OutcomeT], ...] = futures
    while pending:
        try:
            _ = wait(pending, timeout=_STOP_POLL_SECONDS)
        except KeyboardInterrupt:
            continue
        pending = tuple(future for future in pending if not future.done())


def _run_scenario[ResultT: _ScenarioPipelineResult](
    *,
    scenario: CompiledSqlScenario,
    pipeline_result: CompilePipelineResult,
    adapter: BaseAdapter,
    project_name: str,
    source_lexical_syntax: SqlLexicalSyntax,
    execute: Callable[[ScenarioExecutionPlan], ResultT],
    failed: _ScenarioFailureResult[ResultT],
    on_scenario_start: Callable[[CompiledSqlScenario], None] | None,
) -> _ScenarioOutcome[ResultT]:
    scenario_plan: ScenarioExecutionPlan | None = None
    started: float = time.monotonic()
    with ResourceAttemptLifecycle(
        resource_id=_scenario_resource_id(scenario.name),
        resource_kind="scenario",
        resource_name=scenario.name,
        run_id=pipeline_result.project.run_id,
    ) as lifecycle:
        if on_scenario_start is not None:
            on_scenario_start(scenario)
        try:
            scenario_plan = build_scenario_plan(
                scenario=scenario,
                pipeline_result=pipeline_result,
                adapter=adapter,
                project_name=project_name,
                source_lexical_syntax=source_lexical_syntax,
            )
            result: ResultT = execute(scenario_plan)
        except Exception as exc:
            result = failed(scenario_name=scenario.name, exc=exc)
        result = replace(result, duration_ms=(time.monotonic() - started) * 1000)
        if result.status == ExecutionStatus.FAILED:
            lifecycle.failed(error_code=result.error_code)
    return _ScenarioOutcome(
        scenario=scenario,
        scenario_plan=scenario_plan,
        result=result,
        resource_attempt_id=lifecycle.resource_attempt_id,
    )


def _scenario_resource_id(scenario_name: str) -> str:
    return f"sql_scenario:{scenario_name}"


def _prepare_scenario_presentation(*, scenario_name: str, has_completion_callback: bool) -> None:
    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None and has_completion_callback:
        projector.expect_resource_enrichment(resource_name=scenario_name)


def select_scenario_snapshot_capture_candidates(
    *,
    project_dir: Path,
    pipeline_result: CompilePipelineResult,
    scenarios: tuple[CompiledSqlScenario, ...],
    adapter: BaseAdapter,
    project_name: str,
    capture_adapter: str,
    capture_dialect: str,
    refresh: bool,
    source_lexical_syntax: SqlLexicalSyntax,
) -> tuple[str, ...]:
    """Return selected scenario names that need snapshot capture before local replay."""

    names: list[str] = []
    scenario: CompiledSqlScenario
    for scenario in scenarios:
        if refresh:
            names.append(scenario.name)
            continue
        try:
            scenario_plan: ScenarioExecutionPlan = build_scenario_plan(
                scenario=scenario,
                pipeline_result=pipeline_result,
                adapter=adapter,
                project_name=project_name,
                source_lexical_syntax=source_lexical_syntax,
            )
            snapshot_state: ScenarioSnapshotStateResult = classify_scenario_snapshot_state(
                project_dir=project_dir,
                scenario_plan=scenario_plan,
                capture_adapter=capture_adapter,
                capture_dialect=capture_dialect,
            )
        except Exception as error:
            log_debug_event(
                logger=_DEBUG_LOGGER,
                message="scenario snapshot state classification failed; skipping auto-capture",
                scenario=scenario.name,
                sqlbuild_error=str(error),
            )
            continue
        if snapshot_state.state in (ScenarioSnapshotState.MISSING, ScenarioSnapshotState.STALE):
            names.append(scenario.name)
    return tuple(names)
