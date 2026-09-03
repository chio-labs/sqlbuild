"""Canonical lifecycle boundary for one command run."""

from __future__ import annotations

import time
from types import TracebackType

from sqlbuild.runtime.observability._helpers.dispatcher import current_event_dispatcher
from sqlbuild.runtime.observability._helpers.factory import create_lifecycle_event
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.types import JSONValue


class RunLifecycle:
    """Publish one run start and exactly one terminal with bounded counts."""

    def __init__(
        self,
        *,
        run_kind: str,
        selected_count: int,
        configured_concurrency: int,
        worker_count: int,
    ) -> None:
        _validate_run_bounds(
            selected_count=selected_count,
            configured_concurrency=configured_concurrency,
            worker_count=worker_count,
        )
        self._run_kind: str = run_kind
        self._selected_count: int = selected_count
        self._configured_concurrency: int = configured_concurrency
        self._worker_count: int = worker_count
        self._dispatcher: EventDispatcher | None = None
        self._started: float = 0.0
        self._terminal: bool = False
        self._pass_count: int = 0
        self._warn_count: int = 0
        self._fail_count: int = 0

    def __enter__(self) -> RunLifecycle:
        self._dispatcher = current_event_dispatcher()
        self._started = time.monotonic()
        self._publish(
            event_type="run_started",
            payload={
                "run_kind": self._run_kind,
                "selected_count": self._selected_count,
                "configured_concurrency": self._configured_concurrency,
                "worker_count": self._worker_count,
            },
        )
        return self

    def record_pass(self) -> None:
        self._pass_count += 1

    def record_warning(self) -> None:
        self._warn_count += 1

    def record_failure(self) -> None:
        self._fail_count += 1

    def completed(self) -> None:
        self._publish_terminal(
            event_type="run_failed" if self._fail_count else "run_completed",
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, traceback
        if not self._terminal:
            self._publish_terminal(
                event_type="run_failed" if exc_value is not None else "run_completed",
                error=exc_value,
            )

    def _publish_terminal(
        self,
        *,
        event_type: str,
        error: BaseException | None = None,
    ) -> None:
        if self._terminal:
            return
        self._terminal = True
        payload: dict[str, JSONValue] = {
            "run_kind": self._run_kind,
            "duration_ms": int((time.monotonic() - self._started) * 1000),
            "succeeded_count": self._pass_count + self._warn_count,
            "failed_count": self._fail_count,
            "skipped_count": 0,
            "pass_count": self._pass_count,
            "warn_count": self._warn_count,
            "fail_count": self._fail_count,
        }
        if error is not None:
            payload["error_type"] = type(error).__name__
        self._publish(event_type=event_type, payload=payload)

    def _publish(self, *, event_type: str, payload: dict[str, JSONValue]) -> None:
        if self._dispatcher is not None:
            self._dispatcher.publish_lifecycle(
                create_lifecycle_event(event_type=event_type, payload=payload)
            )


def _validate_run_bounds(
    *, selected_count: int, configured_concurrency: int, worker_count: int
) -> None:
    values: tuple[tuple[str, int], ...] = (
        ("selected_count", selected_count),
        ("configured_concurrency", configured_concurrency),
        ("worker_count", worker_count),
    )
    for field_name, value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ObservabilityValidationError(f"{field_name} must be an integer excluding bool")
    if selected_count < 0:
        raise ObservabilityValidationError("selected_count must be nonnegative")
    if configured_concurrency < 1:
        raise ObservabilityValidationError("configured_concurrency must be positive")
    expected_worker_count: int = min(configured_concurrency, selected_count)
    if worker_count != expected_worker_count:
        raise ObservabilityValidationError(
            "worker_count must equal min(configured_concurrency, selected_count)"
        )
