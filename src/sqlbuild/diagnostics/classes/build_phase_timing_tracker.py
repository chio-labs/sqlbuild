"""Invocation-scoped partial build timing tracker."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import ClassVar

from sqlbuild.diagnostics.models import PartialBuildPhaseTimings


class BuildPhaseTimingTracker:
    """Retain disjoint monotonic phase durations across exceptional exits."""

    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic: Callable[[], float] = monotonic
        self._started_at: float = monotonic()
        self.compile_seconds: float | None = None
        self.planning_seconds: float | None = None
        self.connection_preparation_seconds: float | None = None
        self.schema_preparation_seconds: float | None = None
        self.execution_seconds: float | None = None
        self.cost_collection_seconds: float | None = None

    def snapshot(self) -> PartialBuildPhaseTimings:
        """Return currently available phase durations and total wall time."""

        return PartialBuildPhaseTimings(
            compile_seconds=self.compile_seconds,
            planning_seconds=self.planning_seconds,
            connection_preparation_seconds=self.connection_preparation_seconds,
            schema_preparation_seconds=self.schema_preparation_seconds,
            execution_seconds=self.execution_seconds,
            cost_collection_seconds=self.cost_collection_seconds,
            total_seconds=max(0.0, self._monotonic() - self._started_at),
        )

    @classmethod
    def current(cls) -> BuildPhaseTimingTracker | None:
        """Return the active build timing tracker."""

        return cls._current.get()

    @contextmanager
    def scope(self) -> Iterator[None]:
        """Install this tracker for one command invocation and reset it afterward."""

        token: Token[BuildPhaseTimingTracker | None] = self._current.set(self)
        try:
            yield
        finally:
            self._current.reset(token)

    _current: ClassVar[ContextVar[BuildPhaseTimingTracker | None]] = ContextVar(
        "sqlbuild_build_phase_timing_tracker", default=None
    )
