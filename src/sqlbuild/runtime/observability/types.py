"""Type declarations for runtime observability contracts."""

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

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


class ArtifactSubscriber(Protocol):
    def __call__(self, *, sql: str, statement_id: str | None, resource_id: str | None) -> None: ...


class HistorySubscriber(Protocol):
    def __call__(self, event: "LifecycleEvent") -> None: ...

    def record_sql(
        self, *, sql: str, statement_id: str | None, resource_id: str | None
    ) -> None: ...


type LifecycleRegistration = tuple[
    object, KnownLifecycleSubscriber | OpaqueLifecycleSubscriber, bool
]
type DiagnosticRegistration = tuple[object, DiagnosticSubscriber]


class StatementListener(Protocol):
    """In-process callback receiving the SQL text of each finished outermost statement."""

    def __call__(self, *, sql: str) -> None:
        """Handle one statement that finished, successfully or not."""
        ...
