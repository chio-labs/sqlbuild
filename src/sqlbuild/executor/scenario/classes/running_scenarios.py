"""Connections and plans of scenarios running on concurrent workers."""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


class RunningScenarios:
    """Track in-flight worker connections so an interrupt can cancel their statements."""

    def __init__(self, *, adapter: BaseAdapter) -> None:
        self._adapter: BaseAdapter = adapter
        self._lock: threading.RLock = threading.RLock()
        self._connections: dict[int, Any] = {}
        self._started: list[ScenarioExecutionPlan] = []
        self._closed_connection: bool = False

    def start(self, *, scenario_plan: ScenarioExecutionPlan, connection: Any) -> None:
        """Record that a worker began a scenario on a connection."""

        with self._lock:
            self._connections[id(connection)] = connection
            self._started.append(scenario_plan)

    def finish(self, *, connection: Any) -> None:
        """Record that a worker stopped using a connection."""

        with self._lock:
            _ = self._connections.pop(id(connection), None)

    def interrupt(self, *, close_uncancellable: bool = True) -> None:
        """Cancel every in-flight statement, optionally closing connections that cannot cancel."""

        with self._lock:
            connections: tuple[Any, ...] = tuple(self._connections.values())
        connection: Any
        for connection in connections:
            try:
                if not self._adapter.interrupt_connection(connection) and close_uncancellable:
                    self._closed_connection = True
                    self._adapter.close(connection)
            except Exception as exc:
                log_debug_event(
                    logger=_DEBUG_LOGGER,
                    message="scenario statement interrupt failed",
                    sqlbuild_error=str(exc),
                )

    @property
    def started_plans(self) -> tuple[ScenarioExecutionPlan, ...]:
        """Return the plans of every scenario a worker started."""

        with self._lock:
            return tuple(self._started)

    @property
    def closed_connection(self) -> bool:
        """Return whether an interrupt closed a worker connection."""

        return self._closed_connection
