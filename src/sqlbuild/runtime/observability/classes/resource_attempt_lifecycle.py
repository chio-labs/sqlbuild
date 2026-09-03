"""Canonical lifecycle boundary for one executable resource attempt."""

from __future__ import annotations

import re
import time
from contextlib import ExitStack
from types import TracebackType
from uuid import uuid4

from sqlbuild.runtime.observability._helpers.dispatcher import (
    current_event_dispatcher,
    dispatcher_scope,
)
from sqlbuild.runtime.observability._helpers.factory import create_lifecycle_event
from sqlbuild.runtime.observability._helpers.identity import (
    current_execution_identity,
    invocation_scope,
    resource_attempt_scope,
    run_scope,
)
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.constants import (
    RESOURCE_ATTEMPT_SKIPPED_EVENT,
    RESOURCE_SKIP_CODES,
    RESOURCE_SKIP_MODES,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import ExecutionIdentity
from sqlbuild.runtime.observability.types import JSONValue

_ERROR_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ResourceAttemptLifecycle:
    """Publish exactly one start and terminal fact for executable resource work."""

    def __init__(
        self,
        *,
        resource_id: str,
        resource_kind: str,
        resource_name: str,
        attempt_number: int = 1,
        resource_attempt_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self._resource_id: str = resource_id
        self._resource_kind: str = resource_kind
        self._resource_name: str = resource_name
        self._attempt_number: int = attempt_number
        self._resource_attempt_id: str | None = resource_attempt_id
        self._run_id: str | None = run_id
        self._stack: ExitStack = ExitStack()
        self._dispatcher: EventDispatcher | None = None
        self._started_monotonic: float | None = None
        self._terminal: bool = False
        self._entered: bool = False

    def __enter__(self) -> ResourceAttemptLifecycle:
        if self._entered:
            raise ObservabilityValidationError(
                "resource attempt lifecycle cannot be entered more than once"
            )
        self._entered = True
        try:
            identity: ExecutionIdentity | None = current_execution_identity()
            if identity is None:
                identity = self._stack.enter_context(invocation_scope())
            if identity.run_id is None:
                identity = self._stack.enter_context(run_scope(self._run_id or uuid4().hex))
            dispatcher: EventDispatcher | None = current_event_dispatcher()
            if dispatcher is None:
                dispatcher = EventDispatcher()
                self._stack.enter_context(dispatcher_scope(dispatcher))
            self._dispatcher = dispatcher
            attempt_identity: ExecutionIdentity = self._stack.enter_context(
                resource_attempt_scope(
                    resource_id=self._resource_id,
                    resource_attempt_id=self._resource_attempt_id,
                )
            )
            self._resource_attempt_id = attempt_identity.resource_attempt_id
            self._started_monotonic = time.monotonic()
            self._publish(event_type="resource_attempt_started", payload=self._base_payload())
            return self
        except BaseException:
            try:
                self._stack.close()
            except BaseException:
                pass
            self._dispatcher = None
            self._started_monotonic = None
            raise

    @property
    def resource_attempt_id(self) -> str:
        if self._resource_attempt_id is None:
            raise ObservabilityValidationError("resource attempt lifecycle has not started")
        return self._resource_attempt_id

    def completed(self) -> None:
        self._publish_terminal(event_type="resource_attempt_completed")

    def failed(self, *, error: BaseException | None = None, error_code: str | None = None) -> None:
        payload: dict[str, JSONValue] = self._terminal_payload()
        payload["error_type"] = _safe_error_token(
            value="ExecutionFailed" if error is None else type(error).__name__,
            fallback="ExecutionFailed",
        )
        safe_error_code: str | None = _safe_optional_error_code(error_code)
        if safe_error_code is not None:
            payload["error_code"] = safe_error_code
        self._publish_terminal(event_type="resource_attempt_failed", payload=payload)

    def skipped(self, *, skip_code: str, skip_mode: str | None = None) -> None:
        """Publish one bounded logical skip terminal without retaining its user reason."""

        if skip_code not in RESOURCE_SKIP_CODES:
            raise ObservabilityValidationError("skip_code must be a catalogued value")
        if skip_mode is not None and skip_mode not in RESOURCE_SKIP_MODES:
            raise ObservabilityValidationError("skip_mode must be a catalogued value")
        payload: dict[str, JSONValue] = self._terminal_payload()
        payload["skip_code"] = skip_code
        if skip_mode is not None:
            payload["skip_mode"] = skip_mode
        self._publish_terminal(event_type=RESOURCE_ATTEMPT_SKIPPED_EVENT, payload=payload)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, traceback
        try:
            if not self._terminal:
                if exc_value is None:
                    self.completed()
                else:
                    self.failed(error=exc_value)
        finally:
            self._stack.close()

    def _base_payload(self) -> dict[str, JSONValue]:
        return {
            "resource_kind": self._resource_kind,
            "resource_name": self._resource_name,
            "attempt_number": self._attempt_number,
        }

    def _terminal_payload(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = self._base_payload()
        started: float = self._started_monotonic if self._started_monotonic is not None else 0.0
        payload["duration_ms"] = max(0.0, (time.monotonic() - started) * 1000.0)
        return payload

    def _publish(self, *, event_type: str, payload: dict[str, JSONValue]) -> None:
        if self._dispatcher is None:
            return
        self._dispatcher.publish_lifecycle(
            create_lifecycle_event(event_type=event_type, payload=payload)
        )

    def _publish_terminal(
        self, *, event_type: str, payload: dict[str, JSONValue] | None = None
    ) -> None:
        if self._terminal:
            return
        self._terminal = True
        self._publish(
            event_type=event_type,
            payload=self._terminal_payload() if payload is None else payload,
        )


def _safe_error_token(*, value: object, fallback: str) -> str:
    if not isinstance(value, str) or _ERROR_TOKEN_PATTERN.fullmatch(value) is None:
        return fallback
    return value


def _safe_optional_error_code(value: str | None) -> str | None:
    if value is None or _ERROR_TOKEN_PATTERN.fullmatch(value) is None:
        return None
    return value
