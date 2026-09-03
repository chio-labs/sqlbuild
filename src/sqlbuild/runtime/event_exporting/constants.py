"""Destination-neutral event exporter delivery defaults."""

from collections.abc import Mapping
from types import MappingProxyType

from sqlbuild.runtime.observability.constants import LIFECYCLE_EVENT_CATALOG

DEFAULT_EVENT_EXPORT_QUEUE_CAPACITY: int = 1024
DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS: float = 2.0
DEFAULT_EVENT_EXPORT_INVOCATION_TIMEOUT_SECONDS: float = 1.0
DEFAULT_EVENT_EXPORT_NOTIFICATION_QUEUE_CAPACITY: int = 256
DEFAULT_EVENT_EXPORT_HEALTH_INTERVAL_SECONDS: float = 30.0
EVENT_EXPORTER_EVENT_PARAMETER_NAME: str = "event"
EVENT_EXPORT_SEVERITIES: tuple[str, ...] = ("debug", "info", "warning", "error")
EVENT_EXPORT_KINDS: frozenset[str] = frozenset(
    {"invocation", "run", "resource", "operation", "statement", "retry"}
)
INVOCATION_TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {"invocation_completed", "invocation_failed"}
)
EVENT_EXPORT_SEVERITY_RANKS: Mapping[str, int] = MappingProxyType(
    {severity: index for index, severity in enumerate(EVENT_EXPORT_SEVERITIES)}
)
RETRY_EVENT_TYPE: str = "retry_scheduled"
RESOURCE_EVENT_PREFIX: str = "resource"
LIFECYCLE_EXPORT_DIMENSIONS: Mapping[str, tuple[str, str, int]] = MappingProxyType(
    {
        event_type: (
            ("retry", "warning", 1)
            if event_type == RETRY_EVENT_TYPE
            else (
                (
                    "resource"
                    if event_type.split("_", maxsplit=1)[0] == RESOURCE_EVENT_PREFIX
                    else event_type.split("_", maxsplit=1)[0]
                ),
                "error"
                if event_type.endswith("_failed")
                else "info"
                if definition.terminal
                else "debug",
                3 if event_type.endswith("_failed") else 2 if definition.terminal else 0,
            )
        )
        for event_type, definition in LIFECYCLE_EVENT_CATALOG.items()
    }
)
