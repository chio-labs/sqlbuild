"""Monotonic process resource tracker."""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlbuild.diagnostics._helpers.process_resources import read_process_resources
from sqlbuild.diagnostics.models import ProcessResourceUsage


class ProcessResourceTracker:
    """Capture wall and process resource deltas around one command."""

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        resource_reader: Callable[[], tuple[float, float, int | None]] = read_process_resources,
    ) -> None:
        self._monotonic: Callable[[], float] = monotonic
        self._resource_reader: Callable[[], tuple[float, float, int | None]] = resource_reader
        self._started_at: float = monotonic()
        self._started_user, self._started_system, _ = resource_reader()

    def finish(self) -> ProcessResourceUsage:
        """Return elapsed wall/CPU deltas and process peak RSS."""

        user_cpu, system_cpu, max_rss_bytes = self._resource_reader()
        return ProcessResourceUsage(
            wall_seconds=max(0.0, self._monotonic() - self._started_at),
            user_cpu_seconds=max(0.0, user_cpu - self._started_user),
            system_cpu_seconds=max(0.0, system_cpu - self._started_system),
            max_rss_bytes=max_rss_bytes,
        )
