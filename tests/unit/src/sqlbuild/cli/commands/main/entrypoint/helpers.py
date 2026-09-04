"""CLI output capture wiring test helpers."""

from __future__ import annotations

from typing import cast

from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.models import BoundEventExporter
from sqlbuild.runtime.output_capture.models import OutputRecord


def make_event_exporter_scope(*, records: list[OutputRecord]) -> EventExporterCommandScope:
    """Build the existing event-export infrastructure around a fake destination."""

    def export(*, event: object) -> None:
        records.append(cast(OutputRecord, event))

    dispatcher: EventExporterDispatcher = EventExporterDispatcher(
        exporters=(
            BoundEventExporter(
                name="fake_kafka",
                function=export,
                provider_arguments={},
            ),
        )
    )
    return EventExporterCommandScope(dispatcher=dispatcher)
