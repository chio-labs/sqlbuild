"""Project runtime extension discovery entrypoint."""

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.command_output_sinks import (
    bind_command_output_sink_declarations,
    discover_command_output_sink_declarations,
)
from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    bind_event_exporter_declarations,
    discover_event_exporter_declarations,
    discover_provider_classes,
)
from sqlbuild.compiler.discovery._helpers.yml.project import load_project_config
from sqlbuild.compiler.discovery.exceptions import ProjectConfigError
from sqlbuild.compiler.discovery.models import (
    DiscoveredCommandOutputSink,
    DiscoveredCommandOutputSinkDeclaration,
    DiscoveredEventExporter,
    DiscoveredEventExporterDeclaration,
    DiscoveredProvider,
)
from sqlbuild.runtime.event_exporting.main.stricter_severity import stricter_severity
from sqlbuild.spec.contracts.models import (
    LifecycleEventSinkFilterConfig,
    LifecycleEventSinksConfig,
)
from sqlbuild.spec.contracts.types import EventExportSeverity


def discover_runtime_extensions(
    *, project_dir: Path
) -> tuple[
    tuple[DiscoveredProvider, ...],
    tuple[DiscoveredEventExporter, ...],
    tuple[DiscoveredCommandOutputSink, ...],
]:
    """Discover providers and typed sinks at command startup."""

    declarations: tuple[DiscoveredEventExporterDeclaration, ...] = (
        discover_event_exporter_declarations(project_dir=project_dir)
    )
    output_declarations: tuple[DiscoveredCommandOutputSinkDeclaration, ...] = (
        discover_command_output_sink_declarations(project_dir=project_dir)
    )
    if (
        not declarations
        and not output_declarations
        and not (project_dir / "sqlbuild_project.toml").exists()
    ):
        return (), (), ()
    config: LifecycleEventSinksConfig = load_project_config(project_dir=project_dir).sinks.lifecycle
    declaration_names: frozenset[str] = frozenset(item.name for item in declarations)
    unknown_names: frozenset[str] = frozenset(config.named) - declaration_names
    if unknown_names:
        raise ProjectConfigError(
            "sinks.lifecycle.named contains unknown sink(s): " + ", ".join(sorted(unknown_names))
        )
    if not declarations and not output_declarations:
        return (), (), ()
    providers: tuple[DiscoveredProvider, ...] = discover_provider_classes(project_dir=project_dir)
    exporters: tuple[DiscoveredEventExporter, ...] = bind_event_exporter_declarations(
        declarations=declarations,
        project_dir=project_dir,
        providers=providers,
    )
    output_sinks: tuple[DiscoveredCommandOutputSink, ...] = bind_command_output_sink_declarations(
        declarations=output_declarations,
        project_dir=project_dir,
        providers=providers,
    )
    return (
        providers,
        tuple(_apply_runtime_filter(exporter=exporter, config=config) for exporter in exporters),
        output_sinks,
    )


def _apply_runtime_filter(
    *, exporter: DiscoveredEventExporter, config: LifecycleEventSinksConfig
) -> DiscoveredEventExporter:
    kinds: frozenset[str] = exporter.event_kinds
    severity: EventExportSeverity = exporter.min_severity
    filters: tuple[LifecycleEventSinkFilterConfig, ...] = (
        config.defaults,
        config.named.get(exporter.name, LifecycleEventSinkFilterConfig()),
    )
    for runtime_filter in filters:
        if runtime_filter.event_kinds is not None:
            kinds = kinds & runtime_filter.event_kinds
        severity = stricter_severity(first=severity, second=runtime_filter.min_severity)
    return replace(exporter, event_kinds=kinds, min_severity=severity)
