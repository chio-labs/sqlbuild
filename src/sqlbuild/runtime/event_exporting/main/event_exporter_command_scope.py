"""Event exporter command scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.event_exporting._helpers.scope import (
    event_exporter_command_scope as _event_exporter_command_scope,
)
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope


@contextmanager
def event_exporter_command_scope(
    scope: EventExporterCommandScope,
) -> Iterator[EventExporterCommandScope]:
    """Install one command-owned exporter scope."""

    with _event_exporter_command_scope(scope) as installed:
        yield installed
