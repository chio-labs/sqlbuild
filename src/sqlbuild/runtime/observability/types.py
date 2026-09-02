"""Type declarations for runtime observability contracts."""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.runtime.observability.models import (
        DiagnosticLog,
        DispatchFailure,
        LifecycleEvent,
        OpaqueLifecycleEvent,
    )

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | tuple[JSONValue, ...] | Mapping[str, JSONValue]
type Unsubscribe = Callable[[], None]
type KnownLifecycleSubscriber = Callable[[LifecycleEvent], None]
type OpaqueLifecycleSubscriber = Callable[[LifecycleEvent | OpaqueLifecycleEvent], None]
type DiagnosticSubscriber = Callable[[DiagnosticLog], None]
type HealthCallback = Callable[[DispatchFailure], None]
type LifecycleRegistration = tuple[
    object, KnownLifecycleSubscriber | OpaqueLifecycleSubscriber, bool
]
type DiagnosticRegistration = tuple[object, DiagnosticSubscriber]
