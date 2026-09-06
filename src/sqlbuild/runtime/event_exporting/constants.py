"""Destination-neutral event exporter delivery defaults."""

from collections.abc import Mapping
from types import MappingProxyType

from sqlbuild.runtime.event_exporting.types import LifecycleEventKind
from sqlbuild.runtime.observability.constants import LIFECYCLE_EVENT_CATALOG
from sqlbuild.spec.contracts.types import EventExportSeverity

DEFAULT_EVENT_EXPORT_QUEUE_CAPACITY: int = 1024
DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS: float = 2.0
DEFAULT_EVENT_EXPORT_INVOCATION_TIMEOUT_SECONDS: float = 1.0
DEFAULT_EVENT_EXPORT_NOTIFICATION_QUEUE_CAPACITY: int = 256
DEFAULT_EVENT_EXPORT_HEALTH_INTERVAL_SECONDS: float = 30.0
EVENT_EXPORTER_EVENT_PARAMETER_NAME: str = "event"
EVENT_EXPORT_SEVERITIES: tuple[str, ...] = tuple(item.value for item in EventExportSeverity)
EVENT_EXPORT_KINDS: frozenset[str] = frozenset(kind.value for kind in LifecycleEventKind)
INVOCATION_TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {"invocation_completed", "invocation_failed"}
)
EVENT_EXPORT_SEVERITY_RANKS: Mapping[EventExportSeverity, int] = MappingProxyType(
    {severity: index for index, severity in enumerate(EventExportSeverity)}
)
RETRY_EVENT_TYPE: str = "retry_scheduled"
RESOURCE_EVENT_PREFIX: str = "resource"
LIFECYCLE_EXPORT_DIMENSIONS: Mapping[str, tuple[str, EventExportSeverity, int]] = MappingProxyType(
    {
        event_type: (
            ("retry", EventExportSeverity.WARNING, 1)
            if event_type == RETRY_EVENT_TYPE
            else (
                (
                    "resource"
                    if event_type.split("_", maxsplit=1)[0] == RESOURCE_EVENT_PREFIX
                    else event_type.split("_", maxsplit=1)[0]
                ),
                EventExportSeverity.ERROR
                if event_type.endswith("_failed")
                else EventExportSeverity.INFO
                if definition.terminal
                else EventExportSeverity.DEBUG,
                3 if event_type.endswith("_failed") else 2 if definition.terminal else 0,
            )
        )
        for event_type, definition in LIFECYCLE_EVENT_CATALOG.items()
    }
)
