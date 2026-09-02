"""Synchronous in-process observability dispatcher."""

from __future__ import annotations

from contextvars import ContextVar, Token
from functools import partial
from threading import RLock
from typing import Literal, cast, overload

from sqlbuild.runtime.observability._helpers.failure_formatting import (
    _safe_error_message,
    _safe_error_type,
    _safe_subscriber_name,
)
from sqlbuild.runtime.observability._helpers.validation import validate_known_lifecycle_event
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    DispatchFailure,
    LifecycleEvent,
    OpaqueLifecycleEvent,
)
from sqlbuild.runtime.observability.types import (
    DiagnosticRegistration,
    DiagnosticSubscriber,
    HealthCallback,
    KnownLifecycleSubscriber,
    LifecycleRegistration,
    OpaqueLifecycleSubscriber,
    Unsubscribe,
)

_REPORTING_FAILURE: ContextVar[bool] = ContextVar(
    "sqlbuild_observability_reporting_failure", default=False
)


class EventDispatcher:
    """Publish lifecycle facts and diagnostic logs synchronously to ordered snapshots."""

    def __init__(self, *, health_callback: HealthCallback | None = None) -> None:
        self._health_callback: HealthCallback | None = health_callback
        self._lock: RLock = RLock()
        self._lifecycle: tuple[LifecycleRegistration, ...] = ()
        self._diagnostics: tuple[DiagnosticRegistration, ...] = ()

    @overload
    def subscribe_lifecycle(
        self, *, subscriber: KnownLifecycleSubscriber, accepts_opaque: Literal[False]
    ) -> Unsubscribe: ...

    @overload
    def subscribe_lifecycle(
        self, *, subscriber: OpaqueLifecycleSubscriber, accepts_opaque: Literal[True]
    ) -> Unsubscribe: ...

    def subscribe_lifecycle(
        self,
        *,
        subscriber: KnownLifecycleSubscriber | OpaqueLifecycleSubscriber,
        accepts_opaque: bool,
    ) -> Unsubscribe:
        """Register a lifecycle subscriber and return its idempotent unsubscriber."""

        token: object = object()
        registration: LifecycleRegistration = (token, subscriber, accepts_opaque)
        with self._lock:
            self._lifecycle = (*self._lifecycle, registration)
        return partial(self._unsubscribe_lifecycle, token=token)

    def subscribe_diagnostics(self, subscriber: DiagnosticSubscriber) -> Unsubscribe:
        """Register a diagnostic-log subscriber and return its idempotent unsubscriber."""

        token: object = object()
        registration: DiagnosticRegistration = (token, subscriber)
        with self._lock:
            self._diagnostics = (*self._diagnostics, registration)
        return partial(self._unsubscribe_diagnostics, token=token)

    def publish_lifecycle(self, event: LifecycleEvent | OpaqueLifecycleEvent) -> None:
        """Synchronously publish a lifecycle fact to the current ordered snapshot."""

        if not isinstance(event, (LifecycleEvent, OpaqueLifecycleEvent)):
            raise ObservabilityValidationError(
                "lifecycle publication requires LifecycleEvent or OpaqueLifecycleEvent"
            )
        if isinstance(event, LifecycleEvent):
            validate_known_lifecycle_event(event=event)
        with self._lock:
            subscribers: tuple[LifecycleRegistration, ...] = self._lifecycle
        for _, subscriber, accepts_opaque in subscribers:
            if isinstance(event, OpaqueLifecycleEvent) and not accepts_opaque:
                continue
            try:
                opaque_subscriber: OpaqueLifecycleSubscriber = cast(
                    OpaqueLifecycleSubscriber, subscriber
                )
                opaque_subscriber(event)
            except Exception as error:
                self._report_failure(channel="lifecycle", subscriber=subscriber, error=error)

    def publish_diagnostic(self, log: DiagnosticLog) -> None:
        """Synchronously publish a diagnostic log to the current ordered snapshot."""

        if not isinstance(log, DiagnosticLog):
            raise ObservabilityValidationError("diagnostic publication requires DiagnosticLog")
        with self._lock:
            subscribers: tuple[DiagnosticRegistration, ...] = self._diagnostics
        for _, subscriber in subscribers:
            try:
                subscriber(log)
            except Exception as error:
                self._report_failure(channel="diagnostic", subscriber=subscriber, error=error)

    def _unsubscribe_lifecycle(self, *, token: object) -> None:
        with self._lock:
            self._lifecycle = tuple(
                registration for registration in self._lifecycle if registration[0] is not token
            )

    def _unsubscribe_diagnostics(self, *, token: object) -> None:
        with self._lock:
            self._diagnostics = tuple(
                registration for registration in self._diagnostics if registration[0] is not token
            )

    def _report_failure(
        self,
        *,
        channel: Literal["lifecycle", "diagnostic"],
        subscriber: KnownLifecycleSubscriber | OpaqueLifecycleSubscriber | DiagnosticSubscriber,
        error: Exception,
    ) -> None:
        callback: HealthCallback | None = self._health_callback
        if callback is None or _REPORTING_FAILURE.get():
            return
        failure: DispatchFailure = DispatchFailure(
            channel=channel,
            subscriber=_safe_subscriber_name(subscriber=subscriber),
            error_type=_safe_error_type(error=error),
            message=_safe_error_message(error=error),
        )
        token: Token[bool] = _REPORTING_FAILURE.set(True)
        try:
            callback(failure)
        except Exception:
            pass
        finally:
            _REPORTING_FAILURE.reset(token)
