"""Typed event exporter runtime contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting.constants import EVENT_EXPORT_KINDS


@dataclass(frozen=True)
class LifecycleEventSinkDefinition:
    """Immutable metadata attached to a lifecycle-event sink function."""

    name: str
    event_kinds: frozenset[str]
    min_severity: str


@dataclass(frozen=True)
class BoundEventExporter:
    """One validated exporter bound to command-scoped provider instances."""

    name: str
    function: Callable[..., object]
    provider_arguments: Mapping[str, object]
    event_kinds: frozenset[str] = EVENT_EXPORT_KINDS
    min_severity: str = "debug"


@dataclass(frozen=True)
class EventExporterCounts:
    """Frozen attempt counters for one exporter or their aggregate."""

    accepted: int = 0
    filtered: int = 0
    delivered: int = 0
    failed: int = 0
    dropped: int = 0


@dataclass(frozen=True)
class EventExporterAccounting:
    """Frozen accounting snapshot for one named exporter."""

    exporter_name: str
    counts: EventExporterCounts


@dataclass(frozen=True)
class EventExportSummary:
    """Final or point-in-time best-effort delivery accounting."""

    aggregate: EventExporterCounts
    per_exporter: tuple[EventExporterAccounting, ...]
    queue_depth: int
    queue_capacity: int
    flush_complete: bool

    @property
    def accepted(self) -> int:
        return self.aggregate.accepted

    @property
    def filtered(self) -> int:
        return self.aggregate.filtered

    @property
    def delivered(self) -> int:
        return self.aggregate.delivered

    @property
    def failed(self) -> int:
        return self.aggregate.failed

    @property
    def dropped(self) -> int:
        return self.aggregate.dropped


@dataclass(frozen=True)
class EventExporterFailure:
    """Sanitized exporter failure information safe for diagnostics."""

    exporter_name: str
    error_type: str
    event_kind: str
    event_severity: str


@dataclass(frozen=True)
class LifecycleExportPolicy:
    """Catalogued export dimensions for one validated lifecycle type."""

    kind: str
    severity: str
    priority: int


@dataclass(frozen=True)
class QueuedLifecycleEvent:
    """One queued event and its exact eligible exporter attempts."""

    sequence: int
    event: LifecycleEvent
    policy: LifecycleExportPolicy
    eligible_exporters: tuple[int, ...]
