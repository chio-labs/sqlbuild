"""Current CLI event exporter command scope."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredCommandOutputSink,
    DiscoveredEventExporter,
    DiscoveredProjectInputs,
    DiscoveredProvider,
)
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope

_CURRENT_SCOPE: ContextVar[EventExporterCommandScope | None] = ContextVar(
    "sqlbuild_event_exporter_command_scope", default=None
)


@contextmanager
def event_exporter_command_scope(
    scope: EventExporterCommandScope,
) -> Iterator[EventExporterCommandScope]:
    token: Token[EventExporterCommandScope | None] = _CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_SCOPE.reset(token)


def current_event_exporter_command_scope() -> EventExporterCommandScope | None:
    return _CURRENT_SCOPE.get()


def configure_discovered_event_exporters(discovered_inputs: DiscoveredProjectInputs) -> None:
    scope: EventExporterCommandScope | None = current_event_exporter_command_scope()
    if scope is not None:
        scope.configure(discovered_inputs)


def cached_event_exporter_extensions(
    *, project_dir: Path
) -> (
    tuple[
        tuple[DiscoveredProvider, ...],
        tuple[DiscoveredEventExporter, ...],
        tuple[DiscoveredCommandOutputSink, ...],
    ]
    | None
):
    scope: EventExporterCommandScope | None = current_event_exporter_command_scope()
    return None if scope is None else scope.cached_extensions(project_dir=project_dir)
