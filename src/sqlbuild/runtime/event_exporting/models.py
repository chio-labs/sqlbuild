"""Typed lifecycle-event sink declarations."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild._native import EventExportSeverity


@dataclass(frozen=True)
class LifecycleEventSinkDefinition:
    """Immutable metadata attached to a lifecycle-event sink function."""

    name: str
    event_kinds: frozenset[str]
    min_severity: EventExportSeverity
