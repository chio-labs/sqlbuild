"""Lifecycle-event sink declaration constants."""

from sqlbuild._native import EventExportSeverity
from sqlbuild.runtime.event_exporting.types import LifecycleEventKind

EVENT_EXPORTER_EVENT_PARAMETER_NAME: str = "event"
EVENT_EXPORT_SEVERITIES: tuple[str, ...] = tuple(item.value for item in EventExportSeverity)
EVENT_EXPORT_KINDS: frozenset[str] = frozenset(kind.value for kind in LifecycleEventKind)
COMMAND_OUTPUT_SINK_ATTRIBUTE: str = "__sqlbuild_command_output_sink__"
LIFECYCLE_EVENT_SINK_ATTRIBUTE: str = "__sqlbuild_lifecycle_event_sink__"
