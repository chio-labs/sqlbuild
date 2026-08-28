"""Concurrent executor connection setup."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter


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
