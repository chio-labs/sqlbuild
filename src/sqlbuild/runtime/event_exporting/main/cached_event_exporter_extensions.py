"""Cached event exporter extension entrypoint."""

from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredCommandOutputSink,
    DiscoveredEventExporter,
    DiscoveredProvider,
)
from sqlbuild.runtime.event_exporting._helpers.scope import (
    cached_event_exporter_extensions as _cached_event_exporter_extensions,
)


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
    """Return startup-discovered extensions for the active project root."""

    return _cached_event_exporter_extensions(project_dir=project_dir)
