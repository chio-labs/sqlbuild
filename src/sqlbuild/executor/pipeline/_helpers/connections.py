"""Concurrent executor connection setup."""

from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker
from sqlbuild.executor.build.models import BuildCallbacks
from sqlbuild.executor.pipeline._helpers.schema_preparation import prepare_build_schemas
from sqlbuild.executor.pipeline.models import BuildConnectionPreparation


def open_worker_connections(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection_count: int,
) -> tuple[Any, ...]:
    """Open worker connections concurrently and clean up partial success on failure."""

    opened_connections: list[Any] = []
    first_error: BaseException | None = None
    with ThreadPoolExecutor(max_workers=connection_count) as executor:
        futures: tuple[Future[Any], ...] = tuple(
            executor.submit(adapter.connect, connection_config) for _ in range(connection_count)
        )
        future: Future[Any]
        for future in futures:
            try:
                opened_connections.append(future.result())
            except BaseException as error:
                if first_error is None:
                    first_error = error
    if first_error is not None:
        close_connections(
            adapter=adapter,
            connections=tuple(opened_connections),
            active_error=first_error,
        )
        raise first_error
    return tuple(opened_connections)


def close_connections(
    *,
    adapter: BaseAdapter,
    connections: tuple[Any, ...],
    active_error: BaseException | None = None,
) -> None:
    """Attempt every close, raising cleanup failure only when no error is already active."""

    first_close_error: BaseException | None = None
    connection: Any
    for connection in connections:
        try:
            adapter.close(connection)
        except BaseException as error:
            if first_close_error is None:
                first_close_error = error
    if active_error is None and first_close_error is not None:
        raise first_close_error


def prepare_build_connections(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection_count: int,
    callbacks: BuildCallbacks,
) -> BuildConnectionPreparation:
    """Open build connections and prepare schemas with disjoint timings."""

    physical_connection_count: int = connection_count + 1
    if callbacks.on_connection_start is not None:
        callbacks.on_connection_start(physical_connection_count)
    preparation_start: float = time.monotonic()
    connection_seconds: float = 0.0
    schema_seconds: float | None = None
    worker_connections: tuple[Any, ...] = ()
    scheduler_connection: Any | None = None
    try:
        logging.getLogger("sqlbuild.executor.pipeline").debug("open scheduler connection")
        connection_start: float = time.monotonic()
        try:
            scheduler_connection = adapter.connect(connection_config)
        finally:
            connection_seconds += time.monotonic() - connection_start
        schema_start: float = time.monotonic()
        try:
            prepare_build_schemas(
                plan=plan,
                adapter=adapter,
                connection_config=connection_config,
                connection=scheduler_connection,
            )
        finally:
            schema_seconds = time.monotonic() - schema_start
        connection_start = time.monotonic()
        try:
            worker_connections = open_worker_connections(
                adapter=adapter,
                connection_config=connection_config,
                connection_count=connection_count,
            )
        finally:
            connection_seconds += time.monotonic() - connection_start
    except BaseException as error:
        _record_preparation_timings(
            connection_seconds=connection_seconds,
            schema_seconds=schema_seconds,
        )
        if callbacks.on_connection_error is not None:
            callbacks.on_connection_error(
                physical_connection_count,
                elapsed_seconds=time.monotonic() - preparation_start,
            )
        cleanup_connections: tuple[Any, ...] = worker_connections + (
            () if scheduler_connection is None else (scheduler_connection,)
        )
        close_connections(adapter=adapter, connections=cleanup_connections, active_error=error)
        raise
    _record_preparation_timings(
        connection_seconds=connection_seconds,
        schema_seconds=schema_seconds,
    )
    if callbacks.on_connection_complete is not None:
        callbacks.on_connection_complete(
            physical_connection_count,
            elapsed_seconds=time.monotonic() - preparation_start,
        )
    return BuildConnectionPreparation(
        scheduler_connection=scheduler_connection,
        worker_connections=worker_connections,
        connection_seconds=connection_seconds,
        schema_seconds=schema_seconds,
    )


def _record_preparation_timings(*, connection_seconds: float, schema_seconds: float | None) -> None:
    tracker: BuildPhaseTimingTracker | None = BuildPhaseTimingTracker.current()
    if tracker is None:
        return
    tracker.connection_preparation_seconds = connection_seconds
    tracker.schema_preparation_seconds = _combined_phase_seconds(
        first=tracker.schema_preparation_seconds,
        second=schema_seconds,
    )


def _combined_phase_seconds(*, first: float | None, second: float | None) -> float | None:
    if first is None:
        return second
    if second is None:
        return first
    return first + second
