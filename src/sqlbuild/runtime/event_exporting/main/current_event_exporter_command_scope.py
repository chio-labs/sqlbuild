"""Current event exporter command scope entrypoint."""

from sqlbuild.runtime.event_exporting._helpers.scope import (
    current_event_exporter_command_scope as _current_event_exporter_command_scope,
)
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope


def current_event_exporter_command_scope() -> EventExporterCommandScope | None:
    """Return the active command-owned exporter scope, if any."""

    return _current_event_exporter_command_scope()
