"""Mutable load DAG scheduling state."""

from __future__ import annotations

import queue

from sqlbuild.executor.load.models import LoadExecutionResult


class LoadDagState:
    """Mutable scheduling state for concurrent source loader DAG execution."""

    def __init__(
        self,
        *,
        results: list[LoadExecutionResult | None],
        in_degree: dict[str, int],
        ready: list[str],
        in_flight: set[str],
        failed_or_skipped: set[str],
        results_by_name: dict[str, LoadExecutionResult],
        source_index_by_name: dict[str, int],
        downstream_names: dict[str, tuple[str, ...]],
        completion_queue: queue.Queue[tuple[str, LoadExecutionResult]],
    ) -> None:
        self.results = results
        self.in_degree = in_degree
        self.ready = ready
        self.in_flight = in_flight
        self.failed_or_skipped = failed_or_skipped
        self.results_by_name = results_by_name
        self.source_index_by_name = source_index_by_name
        self.downstream_names = downstream_names
        self.completion_queue = completion_queue
