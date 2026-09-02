"""CLI command ownership for exporter delivery and shared providers."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from sqlbuild.compiler.discovery.models import (
    DiscoveredEventExporter,
    DiscoveredProjectInputs,
    DiscoveredProvider,
)
from sqlbuild.provider.classes.session import ProviderSession
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.models import BoundEventExporter, EventExportSummary


class EventExporterCommandScope:
    """Bind discovered exporters and own their command-scoped provider session."""

    def __init__(self, *, dispatcher: EventExporterDispatcher) -> None:
        self.dispatcher = dispatcher
        self.provider_session: ProviderSession | None = None
        self.project_dir: Path | None = None
        self.providers: tuple[DiscoveredProvider, ...] = ()
        self.event_exporters: tuple[DiscoveredEventExporter, ...] = ()
        self._configured = False
        self._close_lock = Lock()
        self._provider_close_registered = False

    def configure(self, discovered_inputs: DiscoveredProjectInputs) -> None:
        """Bind once after normal project discovery has validated declarations."""

        self.configure_extensions(
            providers=discovered_inputs.providers,
            event_exporters=discovered_inputs.event_exporters,
        )

    def configure_extensions(
        self,
        *,
        project_dir: Path | None = None,
        providers: tuple[DiscoveredProvider, ...],
        event_exporters: tuple[DiscoveredEventExporter, ...],
    ) -> None:
        """Bind declarations discovered at the outer command startup boundary."""

        if self._configured:
            return
        self._configured = True
        self.project_dir = project_dir.resolve() if project_dir is not None else None
        self.providers = providers
        self.event_exporters = event_exporters
        if not event_exporters:
            self.dispatcher.bind(())
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
                    )
                )
        except BaseException:
            session.release()
            session.close(force=True)
            raise
        self.provider_session = session
        self.dispatcher.bind(tuple(bindings))

    def cached_extensions(
        self, *, project_dir: Path
    ) -> tuple[tuple[DiscoveredProvider, ...], tuple[DiscoveredEventExporter, ...]] | None:
        """Return startup declarations only for the same project root."""

        if self.project_dir is None or project_dir.resolve() != self.project_dir:
            return None
        return self.providers, self.event_exporters

    def close(self) -> EventExportSummary:
        """Flush exporters before reverse-order provider teardown."""

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
