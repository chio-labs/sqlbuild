"""CLI command ownership for typed sink delivery and shared providers."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from sqlbuild.compiler.discovery.models import (
    DiscoveredCommandOutputSink,
    DiscoveredEventExporter,
    DiscoveredProjectInputs,
    DiscoveredProvider,
)
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.models import BoundEventExporter, EventExportSummary
from sqlbuild.runtime.output_capture.models import (
    BoundCommandOutputSink,
    CommandOutputRecord,
)


class EventExporterCommandScope:
    """Bind discovered typed sinks and own their command-scoped provider session."""

    def __init__(self, *, dispatcher: EventExporterDispatcher) -> None:
        self.dispatcher = dispatcher
        self.provider_session: ProviderSession | None = None
        self.project_dir: Path | None = None
        self.providers: tuple[DiscoveredProvider, ...] = ()
        self.event_exporters: tuple[DiscoveredEventExporter, ...] = ()
        self.command_output_sinks: tuple[DiscoveredCommandOutputSink, ...] = ()
        self._configured = False
        self._close_lock = Lock()
        self._provider_close_registered = False

    def configure(self, discovered_inputs: DiscoveredProjectInputs) -> None:
        """Bind once after normal project discovery has validated declarations."""

        self.configure_extensions(
            providers=discovered_inputs.providers,
            event_exporters=discovered_inputs.event_exporters,
            command_output_sinks=discovered_inputs.command_output_sinks,
        )

    def configure_extensions(
        self,
        *,
        project_dir: Path | None = None,
        providers: tuple[DiscoveredProvider, ...],
        event_exporters: tuple[DiscoveredEventExporter, ...],
        command_output_sinks: tuple[DiscoveredCommandOutputSink, ...] = (),
    ) -> None:
        """Bind declarations discovered at the outer command startup boundary."""

        if self._configured:
            return
        self._configured = True
        self.project_dir = project_dir.resolve() if project_dir is not None else None
        self.providers = providers
        self.event_exporters = event_exporters
        self.command_output_sinks = command_output_sinks
        if not event_exporters and not command_output_sinks:
            self.dispatcher.bind(())
            self.dispatcher.bind_command_output_sinks(())
            return
        session: ProviderSession = build_provider_session(
            discovered_providers=providers,
            allow_shared=False,
        )
        session.hold_open()
        try:
            bindings: list[BoundEventExporter] = []
            for exporter in event_exporters:
                provider_arguments: dict[str, object] = {
                    usage.parameter_name: session.get(usage.provider_name)
                    for usage in exporter.provider_usages
                }
                bindings.append(
                    BoundEventExporter(
                        name=exporter.name,
                        function=exporter.function,
                        provider_arguments=provider_arguments,
                        event_kinds=exporter.event_kinds,
                        min_severity=exporter.min_severity,
                    )
                )
            output_bindings: list[BoundCommandOutputSink] = []
            for sink in command_output_sinks:
                output_provider_arguments: dict[str, object] = {
                    usage.parameter_name: session.get(usage.provider_name)
                    for usage in sink.provider_usages
                }
                output_bindings.append(
                    BoundCommandOutputSink(
                        name=sink.name,
                        function=sink.function,
                        provider_arguments=output_provider_arguments,
                        streams=sink.streams,
                    )
                )
        except BaseException:
            session.release()
            session.close(force=True)
            raise
        self.provider_session = session
        self.dispatcher.bind(tuple(bindings))
        self.dispatcher.bind_command_output_sinks(tuple(output_bindings))

    def cached_extensions(
        self, *, project_dir: Path
    ) -> (
        tuple[
            tuple[DiscoveredProvider, ...],
            tuple[DiscoveredEventExporter, ...],
            tuple[DiscoveredCommandOutputSink, ...],
        ]
        | None
    ):
        """Return startup declarations only for the same project root."""

        if self.project_dir is None or project_dir.resolve() != self.project_dir:
            return None
        return self.providers, self.event_exporters, self.command_output_sinks

    def close(self) -> EventExportSummary:
        """Flush sink delivery before reverse-order provider teardown."""

        summary: EventExportSummary = self.dispatcher.shutdown()
        session: ProviderSession | None = self.provider_session
        with self._close_lock:
            if session is None or self._provider_close_registered:
                return summary
            self._provider_close_registered = True

        def close_provider_session() -> None:
            try:
                session.release()
            finally:
                session.close(force=True)

        self.dispatcher.finalize_when_idle(close_provider_session)
        return summary

    def export_output(self, records: tuple[CommandOutputRecord, ...]) -> None:
        """Reuse bound sink functions and provider instances for output records."""

        self.dispatcher.export_output(records)
