"""Discovered event exporter configuration entrypoint."""

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.runtime.event_exporting._helpers.scope import (
    configure_discovered_event_exporters as _configure_discovered_event_exporters,
)


def configure_discovered_event_exporters(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Configure the active exporter scope from validated discovery inputs."""

    _ = _configure_discovered_event_exporters(discovered_inputs)
