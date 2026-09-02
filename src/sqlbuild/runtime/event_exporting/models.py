"""Typed event exporter runtime contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EventExporterDefinition:
    """Immutable metadata attached to an event exporter function."""

    name: str


@dataclass(frozen=True)
class BoundEventExporter:
    """One validated exporter bound to command-scoped provider instances."""

    name: str
    function: Callable[..., object]
    provider_arguments: Mapping[str, object]


@dataclass(frozen=True)
class EventExportSummary:
    """Aggregate best-effort delivery accounting for one command."""

    delivered: int
    failed: int
    dropped: int


@dataclass(frozen=True)
class EventExporterFailure:
    """Sanitized exporter failure information safe for diagnostics."""

    exporter_name: str
    error_type: str
