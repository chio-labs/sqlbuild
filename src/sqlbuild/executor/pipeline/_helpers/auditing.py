"""Audit execution pipeline."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, replace
from functools import partial
from typing import Any, cast
from uuid import uuid4

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.executor.auditing.main._execute import execute_audit
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline._helpers.connections import (
    close_connections,
    open_worker_connections,
)
from sqlbuild.executor.pipeline.exceptions import AuditConcurrencyError, AuditOutcomeError
from sqlbuild.executor.pipeline.models import AuditPipelineCallbacks
from sqlbuild.executor.scheduling.main._run_worker import run_worker_with_completion
from sqlbuild.observability import RunLifecycle, run_scope
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)


@dataclass(frozen=True)
class _AuditCompletion:
    index: int
    result: AuditExecutionResult | None = None
    error: BaseException | None = None


class _AuditProjection:
    """Indexed terminal state and plan-ordered public projection."""

    def __init__(self, *, entry_count: int) -> None:
        self.results: list[AuditExecutionResult | None] = [None] * entry_count
        self.errors: dict[int, BaseException] = {}
        self._gaps: set[int] = set()
        self._next_index: int = 0

    def consume(
        self,
        *,
        completion: _AuditCompletion,
        entries: tuple[AuditPlanEntry, ...],
        callbacks: AuditPipelineCallbacks,
    ) -> BaseException | None:
        first_error: BaseException | None = None
        try:
            if completion.error is not None:
                self.errors[completion.index] = completion.error
                if callbacks.on_audit_error is not None:
                    callbacks.on_audit_error(entries[completion.index])
            elif completion.result is not None:
                self.results[completion.index] = completion.result
                if callbacks.on_audit_physical_complete is not None:
                    callbacks.on_audit_physical_complete(completion.result)
        except BaseException as error:
            first_error = error
        projection_error: BaseException | None = self._project(
            on_audit_complete=callbacks.on_audit_complete
        )
        return first_error if first_error is not None else projection_error

    def add_gaps(
        self,
        *,
        indexes: set[int],
        on_audit_complete: Callable[[AuditExecutionResult], None] | None,
    ) -> BaseException | None:
        self._gaps.update(indexes)
        return self._project(on_audit_complete=on_audit_complete)

    def project_remaining(
        self, *, on_audit_complete: Callable[[AuditExecutionResult], None] | None
    ) -> BaseException | None:
        return self._project(on_audit_complete=on_audit_complete)

    def ordered_results(self) -> tuple[AuditExecutionResult, ...]:
        return tuple(result for result in self.results if result is not None)

    def _project(
        self, *, on_audit_complete: Callable[[AuditExecutionResult], None] | None
    ) -> BaseException | None:
        first_error: BaseException | None = None
        while self._next_index < len(self.results):
            result: AuditExecutionResult | None = self.results[self._next_index]
            if result is not None:
                self._next_index += 1
                if on_audit_complete is not None:
                    try:
                        on_audit_complete(result)
                    except BaseException as error:
                        if first_error is None:
                            first_error = error
                continue
            if self._next_index in self.errors or self._next_index in self._gaps:
                self._next_index += 1
                continue
            break
        return first_error


def run_audit_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    max_concurrency: int = 1,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
    on_audit_start: Callable[[AuditPlanEntry], None] | None = None,
    on_audit_complete: Callable[[AuditExecutionResult], None] | None = None,
    run_id: str | None = None,
) -> tuple[AuditExecutionResult, ...]:
    """Execute audits while preserving the original optional callback interface."""

    return run_audit_pipeline_with_callbacks(
        plan=plan,
        connection_config=connection_config,
        adapter=adapter,
        max_concurrency=max_concurrency,
        callbacks=AuditPipelineCallbacks(
            on_connection_start=on_connection_start,
            on_connection_complete=on_connection_complete,
            on_connection_error=on_connection_error,
            on_audit_start=on_audit_start,
            on_audit_complete=on_audit_complete,
        ),
        run_id=run_id,
    )


def run_audit_pipeline_with_callbacks(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    max_concurrency: int,
    callbacks: AuditPipelineCallbacks,
    run_id: str | None = None,
) -> tuple[AuditExecutionResult, ...]:
    """Execute selected audits with bounded workers and split physical/public callbacks."""

    if max_concurrency < 1:
        raise AuditConcurrencyError("audit concurrency must be >= 1")
    entries: tuple[AuditPlanEntry, ...] = plan.audit_entries
    worker_count: int = min(max_concurrency, len(entries))
    canonical_run_id: str = run_id or uuid4().hex
    with run_scope(canonical_run_id) as identity:
        with diagnostics_context(
            sqlbuild_invocation_id=identity.invocation_id,
            sqlbuild_run_id=identity.run_id,
            sqlbuild_configured_concurrency=max_concurrency,
            sqlbuild_worker_count=worker_count,
        ):
            with (
                RunLifecycle(
                    run_kind="audit",
                    selected_count=len(entries),
                    configured_concurrency=max_concurrency,
                    worker_count=worker_count,
                ) as lifecycle,
                CostContext.scope(
                    run_id=canonical_run_id,
                    resource_type="run",
                    resource_name="audit",
                    phase="audit",
                ),
            ):
                execution_callbacks: AuditPipelineCallbacks = replace(
                    callbacks,
                    on_audit_complete=_AuditCompletionRecorder(
                        lifecycle=lifecycle,
                        callback=callbacks.on_audit_complete,
                    ),
                )
                results: tuple[AuditExecutionResult, ...] = _run_audits(
                    entries=entries,
                    plan=plan,
                    connection_config=connection_config,
                    adapter=adapter,
                    worker_count=worker_count,
                    callbacks=execution_callbacks,
                    run_id=canonical_run_id,
                )
                lifecycle.completed()
                return results


class _AuditCompletionRecorder:
    def __init__(
        self,
        *,
        lifecycle: RunLifecycle,
        callback: Callable[[AuditExecutionResult], None] | None,
    ) -> None:
        self._lifecycle: RunLifecycle = lifecycle
        self._callback: Callable[[AuditExecutionResult], None] | None = callback

    def __call__(self, result: AuditExecutionResult) -> None:
        if result.outcome == AuditOutcome.PASS:
            self._lifecycle.record_pass()
        elif result.outcome == AuditOutcome.WARN:
            self._lifecycle.record_warning()
        elif result.outcome == AuditOutcome.ERROR:
            self._lifecycle.record_failure()
        else:
            raise AuditOutcomeError(f"unknown audit outcome: {result.outcome!r}")
        if self._callback is not None:
            self._callback(result)


def _run_audits(
    *,
    entries: tuple[AuditPlanEntry, ...],
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    worker_count: int,
    callbacks: AuditPipelineCallbacks,
    run_id: str,
) -> tuple[AuditExecutionResult, ...]:
    if not entries:
        return ()
    if callbacks.on_connection_start is not None:
        callbacks.on_connection_start(worker_count)
    connection_started: float = time.monotonic()
    try:
        connections: tuple[Any, ...] = open_worker_connections(
            adapter=adapter,
            connection_config=connection_config,
            connection_count=worker_count,
        )
    except BaseException:
        if callbacks.on_connection_error is not None:
            try:
                callbacks.on_connection_error(
                    worker_count, elapsed_seconds=time.monotonic() - connection_started
                )
            except BaseException:
                pass
        raise
    active_error: BaseException | None = None
    try:
        if callbacks.on_connection_complete is not None:
            callbacks.on_connection_complete(
                worker_count, elapsed_seconds=time.monotonic() - connection_started
            )
        if worker_count == 1:
            results: tuple[AuditExecutionResult, ...] = _run_serial_audits(
                entries=entries,
                plan=plan,
                adapter=adapter,
                connection=connections[0],
                callbacks=callbacks,
                run_id=run_id,
            )
        else:
            results = _run_concurrent_audits(
                entries=entries,
                plan=plan,
                adapter=adapter,
                connections=connections,
                worker_count=worker_count,
                callbacks=callbacks,
                run_id=run_id,
            )
        return results
    except BaseException as error:
        active_error = error
        raise
    finally:
        close_connections(adapter=adapter, connections=connections, active_error=active_error)


def _run_serial_audits(
    *,
    entries: tuple[AuditPlanEntry, ...],
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    callbacks: AuditPipelineCallbacks,
    run_id: str,
) -> tuple[AuditExecutionResult, ...]:
    results: list[AuditExecutionResult] = []
    for entry in entries:
        try:
            result: AuditExecutionResult = _execute_entry(
                entry=entry,
                plan=plan,
                adapter=adapter,
                connection=connection,
                on_audit_start=callbacks.on_audit_start,
                run_id=run_id,
            )
        except BaseException:
            if callbacks.on_audit_error is not None:
                callbacks.on_audit_error(entry)
            raise
        results.append(result)
        if callbacks.on_audit_physical_complete is not None:
            callbacks.on_audit_physical_complete(result)
        if callbacks.on_audit_complete is not None:
            callbacks.on_audit_complete(result)
    return tuple(results)


def _run_concurrent_audits(
    *,
    entries: tuple[AuditPlanEntry, ...],
    plan: PlanOutput,
    adapter: BaseAdapter,
    connections: tuple[Any, ...],
    worker_count: int,
    callbacks: AuditPipelineCallbacks,
    run_id: str,
) -> tuple[AuditExecutionResult, ...]:
    connection_pool: queue.Queue[Any] = queue.Queue()
    for connection in connections:
        connection_pool.put(connection)
    completions: queue.Queue[_AuditCompletion] = queue.Queue()
    projection: _AuditProjection = _AuditProjection(entry_count=len(entries))
    futures: dict[int, Future[None]] = {}
    in_flight: set[int] = set()
    next_index: int = 0
    scheduler_error: BaseException | None = None
    pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=worker_count)

    try:
        while next_index < len(entries) and len(in_flight) < worker_count:
            futures[next_index] = _submit_audit(
                pool=pool,
                index=next_index,
                entry=entries[next_index],
                plan=plan,
                adapter=adapter,
                connection_pool=connection_pool,
                completions=completions,
                on_audit_start=callbacks.on_audit_start,
                run_id=run_id,
            )
            in_flight.add(next_index)
            next_index += 1
        while in_flight:
            try:
                completion: _AuditCompletion = completions.get()
            except BaseException as error:
                scheduler_error = error
                break
            in_flight.remove(completion.index)
            completion_error: BaseException | None = projection.consume(
                completion=completion,
                entries=entries,
                callbacks=callbacks,
            )
            if scheduler_error is None and completion_error is not None:
                scheduler_error = completion_error
            if not projection.errors and scheduler_error is None and next_index < len(entries):
                futures[next_index] = _submit_audit(
                    pool=pool,
                    index=next_index,
                    entry=entries[next_index],
                    plan=plan,
                    adapter=adapter,
                    connection_pool=connection_pool,
                    completions=completions,
                    on_audit_start=callbacks.on_audit_start,
                    run_id=run_id,
                )
                in_flight.add(next_index)
                next_index += 1
            elif projection.errors or scheduler_error is not None:
                in_flight, canceled = _cancel_not_started(futures=futures, in_flight=in_flight)
                projection_error: BaseException | None = projection.add_gaps(
                    indexes=canceled,
                    on_audit_complete=callbacks.on_audit_complete,
                )
                if scheduler_error is None and projection_error is not None:
                    scheduler_error = projection_error
        if scheduler_error is not None:
            in_flight, canceled = _cancel_not_started(futures=futures, in_flight=in_flight)
            _ = projection.add_gaps(
                indexes=canceled,
                on_audit_complete=callbacks.on_audit_complete,
            )
    except BaseException as error:
        if scheduler_error is None:
            scheduler_error = error
        in_flight, canceled = _cancel_not_started(futures=futures, in_flight=in_flight)
        _ = projection.add_gaps(
            indexes=canceled,
            on_audit_complete=callbacks.on_audit_complete,
        )
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    while in_flight:
        completion = completions.get()
        in_flight.remove(completion.index)
        completion_error = projection.consume(
            completion=completion,
            entries=entries,
            callbacks=callbacks,
        )
        if scheduler_error is None and completion_error is not None:
            scheduler_error = completion_error
    projection_error = projection.project_remaining(
        on_audit_complete=callbacks.on_audit_complete,
    )
    if scheduler_error is None and projection_error is not None:
        scheduler_error = projection_error
    if scheduler_error is not None:
        raise scheduler_error
    if projection.errors:
        raise projection.errors[min(projection.errors)]
    return projection.ordered_results()


def _submit_audit(  # noqa: PLR0913
    *,
    pool: ThreadPoolExecutor,
    index: int,
    entry: AuditPlanEntry,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection_pool: queue.Queue[Any],
    completions: queue.Queue[_AuditCompletion],
    on_audit_start: Callable[[AuditPlanEntry], None] | None,
    run_id: str,
) -> Future[None]:
    worker: Callable[[], None] = partial(
        run_worker_with_completion,
        key=index,
        connection_pool=connection_pool,
        completion_queue=completions,
        execute=lambda connection: _execute_entry(
            entry=entry,
            plan=plan,
            adapter=adapter,
            connection=connection,
            on_audit_start=on_audit_start,
            run_id=run_id,
        ),
        build_success=lambda key, result: _AuditCompletion(index=key, result=result),
        build_failure=lambda key, error: _AuditCompletion(index=key, error=error),
    )
    return cast(Future[None], pool.submit(copy_context().run, worker))


def _cancel_not_started(
    *, futures: dict[int, Future[None]], in_flight: set[int]
) -> tuple[set[int], set[int]]:
    canceled: set[int] = {index for index in in_flight if futures[index].cancel()}
    return in_flight - canceled, canceled


def _execute_entry(
    *,
    entry: AuditPlanEntry,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    on_audit_start: Callable[[AuditPlanEntry], None] | None,
    run_id: str,
) -> AuditExecutionResult:
    with ResourceAttemptLifecycle(
        resource_id=audit_resource_id(
            audit_name=entry.name,
            attachment_kind=entry.attachment_kind,
            attached_target_kind=entry.attached_target_kind,
            attached_target_name=entry.attached_target_name,
            attached_column_name=entry.attached_column_name,
        ),
        resource_kind="audit",
        resource_name=entry.name,
        run_id=run_id,
    ) as lifecycle:
        if on_audit_start is not None:
            on_audit_start(entry)
        result: AuditExecutionResult = execute_audit(
            audit=entry,
            adapter=adapter,
            connection=connection,
            model_locations=plan.model_locations,
            seed_locations=plan.seed_locations,
            source_map=plan.source_map,
            relation_overrides=None,
            run_scope_phase=AuditRunScope.FINAL,
            quality_scope="standalone",
        )
        if result.outcome == AuditOutcome.ERROR:
            lifecycle.failed()
    return result
