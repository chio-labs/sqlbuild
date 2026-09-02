"""Project runtime extension discovery entrypoint."""

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    bind_event_exporter_declarations,
    discover_event_exporter_declarations,
    discover_provider_classes,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredEventExporter,
    DiscoveredEventExporterDeclaration,
    DiscoveredProvider,
)


def discover_runtime_extensions(
    *, project_dir: Path
) -> tuple[tuple[DiscoveredProvider, ...], tuple[DiscoveredEventExporter, ...]]:
    """Discover providers and event exporters at command startup."""

    declarations: tuple[DiscoveredEventExporterDeclaration, ...] = (
        discover_event_exporter_declarations(project_dir=project_dir)
    )
    if not declarations:
        return (), ()
    providers: tuple[DiscoveredProvider, ...] = discover_provider_classes(project_dir=project_dir)
    exporters: tuple[DiscoveredEventExporter, ...] = bind_event_exporter_declarations(
        declarations=declarations,
        project_dir=project_dir,
        providers=providers,
    )
    return providers, exporters
