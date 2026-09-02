"""Canonical lifecycle boundary for framework-owned non-SQL blocking work."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future
from contextlib import ExitStack
from types import TracebackType
from typing import Any

from sqlbuild.runtime.observability._helpers.dispatcher import (
    current_event_dispatcher,
    dispatcher_scope,
)
from sqlbuild.runtime.observability._helpers.factory import create_lifecycle_event
from sqlbuild.runtime.observability._helpers.identity import (
    current_execution_identity,
    invocation_scope,
    operation_scope,
)
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.constants import (
    HOOK_PHASES,
    HOOK_TYPES,
    OPERATION_KINDS,
    OPERATION_METADATA_FIELDS,
    OPERATION_NAMES,
    RETRY_SCHEDULED_EVENT,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import ExecutionIdentity
from sqlbuild.runtime.observability.types import JSONValue

_ERROR_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_HOOK_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class OperationLifecycle:
    """Publish one start and one terminal fact around owned blocking work."""

    def __init__(
        self,
        *,
        operation_kind: str,
        operation_name: str,
        metadata: Mapping[str, int] | None = None,
        operation_id: str | None = None,
        hook_phase: str | None = None,
        hook_index: int | None = None,
        hook_type: str | None = None,
        hook_name: str | None = None,
        auto_fail_base_exceptions: bool = True,
    ) -> None:
        _validate_catalog_value(
            value=operation_kind, allowed=OPERATION_KINDS, field_name="operation_kind"
        )
        _validate_catalog_value(
            value=operation_name, allowed=OPERATION_NAMES, field_name="operation_name"
        )
        self._operation_kind: str = operation_kind
        self._operation_name: str = operation_name
        self._metadata: dict[str, int] = _validated_metadata(metadata)
        self._operation_id: str | None = operation_id
        self._hook_fields: dict[str, JSONValue] = _validated_hook_fields(
            hook_phase=hook_phase,
            hook_index=hook_index,
            hook_type=hook_type,
            hook_name=hook_name,
        )
        self._auto_fail_base_exceptions: bool = auto_fail_base_exceptions
        self._stack: ExitStack = ExitStack()
        self._dispatcher: EventDispatcher | None = None
        self._started_monotonic: float | None = None
        self._terminal = False
        self._entered = False

    def __enter__(self) -> OperationLifecycle:
        if self._entered:
            raise ObservabilityValidationError(
                "operation lifecycle cannot be entered more than once"
            )
        self._entered = True
        try:
            if current_execution_identity() is None:
                self._stack.enter_context(invocation_scope())
            dispatcher: EventDispatcher | None = current_event_dispatcher()
            if dispatcher is None:
                dispatcher = EventDispatcher()
                self._stack.enter_context(dispatcher_scope(dispatcher))
            identity: ExecutionIdentity = self._stack.enter_context(
                operation_scope(self._operation_id)
            )
            self._operation_id = identity.operation_id
            self._dispatcher = dispatcher
            self._started_monotonic = time.monotonic()
            self._publish(event_type="operation_started", payload=self._base_payload())
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
    def operation_id(self) -> str:
        if self._operation_id is None:
            raise ObservabilityValidationError("operation lifecycle has not started")
        return self._operation_id

    def run[RESULT](self, function: Callable[[], RESULT]) -> RESULT:
        """Own a synchronous callable through its return or exception."""

        with self:
            return function()

    def result[RESULT](self, future: Future[RESULT]) -> RESULT:
        """Own submitted work through the future result boundary."""

        with self:
            return future.result()

    def consume[ITEM](self, iterable: Iterable[ITEM]) -> tuple[ITEM, ...]:
        """Own an iterable through exhaustion and return its consumed values."""

        with self:
            return tuple(iterable)

    def completed(
        self,
        *,
        metadata: Mapping[str, int] | None = None,
        exit_code: int | None = None,
        process_id: int | None = None,
        signal_number: int | None = None,
    ) -> None:
        payload: dict[str, JSONValue] = self._terminal_payload(metadata=metadata)
        payload = _with_process_metadata(
            payload=payload,
            exit_code=exit_code,
            process_id=process_id,
            signal_number=signal_number,
        )
        self._publish_terminal(
            event_type="operation_completed",
            payload=payload,
        )

    def failed(
        self,
        *,
        error: BaseException | None = None,
        error_code: str | None = None,
        metadata: Mapping[str, int] | None = None,
        exit_code: int | None = None,
        process_id: int | None = None,
        signal_number: int | None = None,
    ) -> None:
        payload: dict[str, JSONValue] = self._terminal_payload(metadata=metadata)
        payload = _with_process_metadata(
            payload=payload,
            exit_code=exit_code,
            process_id=process_id,
            signal_number=signal_number,
        )
        payload["error_type"] = _safe_error_token(
            value="ExecutionFailed" if error is None else type(error).__name__,
            fallback="ExecutionFailed",
        )
        resolved_error_code: str | None = (
            _safe_optional_error_code(error_code)
            if error_code is not None
            else (_error_code(error=error) if error is not None else None)
        )
        if resolved_error_code is not None:
            payload["error_code"] = resolved_error_code
        self._publish_terminal(event_type="operation_failed", payload=payload)

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
                elif isinstance(exc_value, Exception) or self._auto_fail_base_exceptions:
                    self.failed(error=exc_value)
        finally:
            self._stack.close()

    def _base_payload(self) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = {
            "operation_kind": self._operation_kind,
            "operation_name": self._operation_name,
        }
        if self._metadata:
            payload["metadata"] = self._metadata
        payload.update(self._hook_fields)
        return payload

    def _terminal_payload(
        self, *, metadata: Mapping[str, int] | None = None
    ) -> dict[str, JSONValue]:
        payload: dict[str, JSONValue] = self._base_payload()
        terminal_metadata: dict[str, int] = _validated_metadata(metadata)
        if terminal_metadata:
            payload["metadata"] = {**self._metadata, **terminal_metadata}
        started: float = self._started_monotonic if self._started_monotonic is not None else 0.0
        payload["duration_ms"] = max(0.0, (time.monotonic() - started) * 1000.0)
        return payload

    def _publish(self, *, event_type: str, payload: Mapping[str, JSONValue]) -> None:
        if self._dispatcher is None:
            raise ObservabilityValidationError("operation lifecycle has not started")
        self._dispatcher.publish_lifecycle(
            create_lifecycle_event(event_type=event_type, payload=payload)
        )

    def _publish_terminal(self, *, event_type: str, payload: Mapping[str, JSONValue]) -> None:
        if self._terminal:
            return
        self._terminal = True
        self._publish(event_type=event_type, payload=payload)


def publish_retry_scheduled(
    *,
    failed_attempt_number: int,
    next_attempt_number: int,
    delay_ms: int,
    error: BaseException,
) -> None:
    """Publish one bounded retry decision before the caller blocks for its delay."""

    dispatcher: EventDispatcher | None = current_event_dispatcher()
    if dispatcher is None:
        return
    payload: dict[str, JSONValue] = {
        "failed_attempt_number": failed_attempt_number,
        "next_attempt_number": next_attempt_number,
        "delay_ms": delay_ms,
        "error_type": _safe_error_token(value=type(error).__name__, fallback="ExecutionFailed"),
    }
    error_code: str | None = _error_code(error=error)
    if error_code is not None:
        payload["error_code"] = error_code
    dispatcher.publish_lifecycle(
        create_lifecycle_event(event_type=RETRY_SCHEDULED_EVENT, payload=payload)
    )


def _validate_catalog_value(*, value: str, allowed: frozenset[str], field_name: str) -> None:
    if value not in allowed:
        raise ObservabilityValidationError(f"{field_name} must be a catalogued value")


def _validated_metadata(metadata: Mapping[str, int] | None) -> dict[str, int]:
    if metadata is None:
        return {}
    unexpected: set[str] = set(metadata) - OPERATION_METADATA_FIELDS
    if unexpected:
        raise ObservabilityValidationError("operation metadata contains a non-allowlisted field")
    result: dict[str, int] = {}
    for key, value in metadata.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ObservabilityValidationError(
                "operation metadata values must be nonnegative integers excluding bool"
            )
        result[key] = value
    return result


def _validated_hook_fields(
    *,
    hook_phase: str | None,
    hook_index: int | None,
    hook_type: str | None,
    hook_name: str | None,
) -> dict[str, JSONValue]:
    supplied: bool = any(
        value is not None for value in (hook_phase, hook_index, hook_type, hook_name)
    )
    if not supplied:
        return {}
    if hook_phase not in HOOK_PHASES:
        raise ObservabilityValidationError("hook_phase must be a catalogued value")
    if hook_type not in HOOK_TYPES:
        raise ObservabilityValidationError("hook_type must be a catalogued value")
    if isinstance(hook_index, bool) or not isinstance(hook_index, int) or hook_index < 0:
        raise ObservabilityValidationError("hook_index must be a nonnegative integer")
    result: dict[str, JSONValue] = {
        "hook_phase": hook_phase,
        "hook_index": hook_index,
        "hook_type": hook_type,
    }
    if hook_name is not None and _HOOK_NAME_PATTERN.fullmatch(hook_name) is not None:
        result["hook_name"] = hook_name
    return result


def _safe_error_token(*, value: object, fallback: str) -> str:
    if not isinstance(value, str) or _ERROR_TOKEN_PATTERN.fullmatch(value) is None:
        return fallback
    return value


def _with_process_metadata(
    *,
    payload: dict[str, JSONValue],
    exit_code: int | None,
    process_id: int | None,
    signal_number: int | None,
) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = dict(payload)
    if exit_code is not None:
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ObservabilityValidationError("exit_code must be an integer excluding bool")
        result["exit_code"] = exit_code
    for field_name, value in (("process_id", process_id), ("signal_number", signal_number)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ObservabilityValidationError(
                f"{field_name} must be a nonnegative integer excluding bool"
            )
        result[field_name] = value
    return result


def _error_code(*, error: BaseException) -> str | None:
    for attribute in ("sqlstate", "code", "errno"):
        value: Any | None = getattr(error, attribute, None)
        if isinstance(value, bool) or not isinstance(value, str | int):
            continue
        code: str = str(value)
        if _ERROR_TOKEN_PATTERN.fullmatch(code) is not None:
            return code
    return None


def _safe_optional_error_code(value: str | None) -> str | None:
    if value is None or _ERROR_TOKEN_PATTERN.fullmatch(value) is None:
        return None
    return value
