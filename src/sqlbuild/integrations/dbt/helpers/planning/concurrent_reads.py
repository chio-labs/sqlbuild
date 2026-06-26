"""Run independent warehouse state reads concurrently on per-task connections."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter


def run_state_reads_in_parallel[ReadResult](
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    reads: Mapping[str, Callable[[Any], ReadResult]],
) -> dict[str, ReadResult]:
    """Run each read on its own fresh connection concurrently and return results by name."""

    if not reads:
        return {}

    def run_on_fresh_connection(read: Callable[[Any], ReadResult]) -> ReadResult:
        connection: Any = adapter.connect(connection_config)
        try:
            return read(connection)
        finally:
            adapter.close(connection)

    with ThreadPoolExecutor(max_workers=len(reads)) as pool:
        futures: dict[str, Future[ReadResult]] = {
            name: pool.submit(run_on_fresh_connection, read) for name, read in reads.items()
        }
        return {name: future.result() for name, future in futures.items()}
