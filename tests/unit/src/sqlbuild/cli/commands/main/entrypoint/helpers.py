"""CLI output capture wiring test helpers."""

from __future__ import annotations

from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.output_capture.models import (
    BoundCommandOutputSink,
    CommandOutputRecord,
)
from sqlbuild.sinks import CommandOutputStream


def make_event_exporter_scope(*, records: list[CommandOutputRecord]) -> EventExporterCommandScope:
    """Build the command-scoped sink infrastructure around a fake destination."""

    def export(*, record: CommandOutputRecord) -> None:
        records.append(record)

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(exporters=())
    dispatcher.bind_command_output_sinks(
        (
            BoundCommandOutputSink(
                name="fake_kafka",
                function=export,
                provider_arguments={},
                streams=frozenset(CommandOutputStream),
            ),
        )
    )
    return EventExporterCommandScope(dispatcher=dispatcher)
