"""Project runtime extension discovery entrypoint."""

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    bind_event_exporter_declarations,
    discover_event_exporter_declarations,
    discover_provider_classes,
)
from sqlbuild.compiler.discovery._helpers.yml.project import load_project_config
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.discovery.models import (
    DiscoveredEventExporter,
    DiscoveredEventExporterDeclaration,
    DiscoveredProvider,
)
from sqlbuild.runtime.event_exporting.main.stricter_severity import stricter_severity
from sqlbuild.spec.contracts.models import EventExporterFilterConfig, EventExportersConfig


def discover_runtime_extensions(
    *, project_dir: Path
) -> tuple[tuple[DiscoveredProvider, ...], tuple[DiscoveredEventExporter, ...]]:
    """Discover providers and event exporters at command startup."""

    declarations: tuple[DiscoveredEventExporterDeclaration, ...] = (
        discover_event_exporter_declarations(project_dir=project_dir)
    )
    if not declarations and not (project_dir / "sqlbuild_project.toml").exists():
        return (), ()
    config: EventExportersConfig = load_project_config(project_dir=project_dir).event_exporters
    declaration_names: frozenset[str] = frozenset(item.name for item in declarations)
    unknown_names: frozenset[str] = frozenset(config.named) - declaration_names
    if unknown_names:
        raise ProjectConfigError(
            "event_exporters.named contains unknown exporter(s): "
            + ", ".join(sorted(unknown_names))
        )
    if not declarations:
        return (), ()
    providers: tuple[DiscoveredProvider, ...] = discover_provider_classes(project_dir=project_dir)
    exporters: tuple[DiscoveredEventExporter, ...] = bind_event_exporter_declarations(
        declarations=declarations,
        project_dir=project_dir,
        providers=providers,
    )
    return providers, tuple(
        _apply_runtime_filter(exporter=exporter, config=config) for exporter in exporters
    )


def _apply_runtime_filter(
    *, exporter: DiscoveredEventExporter, config: EventExportersConfig
) -> DiscoveredEventExporter:
    kinds: frozenset[str] = exporter.event_kinds
    severity: str = exporter.min_severity
    filters: tuple[EventExporterFilterConfig, ...] = (
        config.defaults,
        config.named.get(exporter.name, EventExporterFilterConfig()),
    )
    for runtime_filter in filters:
        if runtime_filter.event_kinds is not None:
            kinds = kinds & runtime_filter.event_kinds
        severity = stricter_severity(first=severity, second=runtime_filter.min_severity)
    return replace(exporter, event_kinds=kinds, min_severity=severity)
