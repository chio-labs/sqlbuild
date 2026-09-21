"""Lifecycle facts for one active microbatch interval."""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from types import TracebackType

from sqlbuild.runtime.observability._helpers.dispatcher import current_event_dispatcher
from sqlbuild.runtime.observability._helpers.factory import create_lifecycle_event
from sqlbuild.runtime.observability._helpers.identity import current_execution_identity
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import ExecutionIdentity, MicrobatchLifecycleContext
from sqlbuild.runtime.observability.types import JSONValue

_ERROR_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class MicrobatchLifecycle:
    """Publish the active bounds and terminal outcome for one microbatch."""

    def __init__(
        self,
        *,
        context: MicrobatchLifecycleContext,
    ) -> None:
        self._payload: dict[str, JSONValue] = context.payload()
        self._dispatcher: EventDispatcher | None = None
        self._started_monotonic: float | None = None
        self._terminal: bool = False
        self._entered: bool = False

    def __enter__(self) -> MicrobatchLifecycle:
        if self._entered:
            raise ObservabilityValidationError(
                "microbatch lifecycle cannot be entered more than once"
            )
        self._entered = True
        identity: ExecutionIdentity | None = current_execution_identity()
        dispatcher: EventDispatcher | None = current_event_dispatcher()
        if (
            identity is None
            or identity.run_id is None
            or identity.resource_id is None
            or identity.resource_attempt_id is None
            or dispatcher is None
        ):
            return self
        self._dispatcher = dispatcher
        self._started_monotonic = time.monotonic()
        self._publish(event_type="microbatch_started", payload=self._payload)
        return self

    def start(self) -> None:
        """Publish the start fact without requiring context-manager ownership."""

        self.__enter__()

    def completed(self, *, affected_rows: int | None = None) -> None:
        payload: dict[str, JSONValue] = self._terminal_payload()
        if affected_rows is not None:
            payload["affected_rows"] = affected_rows
        self._publish_terminal(event_type="microbatch_completed", payload=payload)

    def failed(
        self,
        *,
        error: BaseException | None = None,
        error_code: str | None = None,
    ) -> None:
        payload: dict[str, JSONValue] = self._terminal_payload()
        payload["error_type"] = _safe_error_token(
            value="ExecutionFailed" if error is None else type(error).__name__,
            fallback="ExecutionFailed",
        )
        safe_error_code: str | None = _safe_optional_error_code(error_code)
        if safe_error_code is not None:
            payload["error_code"] = safe_error_code
        self._publish_terminal(event_type="microbatch_failed", payload=payload)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, traceback
        if not self._terminal:
            if exc_value is None:
                self.completed()
            else:
                self.failed(error=exc_value)

    def _terminal_payload(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = dict(self._payload)
        started: float = self._started_monotonic if self._started_monotonic is not None else 0.0
        payload["duration_ms"] = max(0.0, (time.monotonic() - started) * 1000.0)
        return payload

    def _publish(self, *, event_type: str, payload: Mapping[str, JSONValue]) -> None:
        if self._dispatcher is None:
            return
        self._dispatcher.publish_lifecycle(
            create_lifecycle_event(event_type=event_type, payload=payload)
        )

    def _publish_terminal(self, *, event_type: str, payload: Mapping[str, JSONValue]) -> None:
        if self._terminal:
            return
        self._terminal = True
        self._publish(event_type=event_type, payload=payload)


def _safe_error_token(*, value: object, fallback: str) -> str:
    if not isinstance(value, str) or _ERROR_TOKEN_PATTERN.fullmatch(value) is None:
        return fallback
    return value


def _safe_optional_error_code(value: str | None) -> str | None:
    if value is None or _ERROR_TOKEN_PATTERN.fullmatch(value) is None:
        return None
    return value
