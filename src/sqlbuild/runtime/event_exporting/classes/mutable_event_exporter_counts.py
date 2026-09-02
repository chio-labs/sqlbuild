"""Mutable dispatcher accounting state."""

from sqlbuild.runtime.event_exporting.models import EventExporterCounts


class MutableEventExporterCounts:
    """Dispatcher-owned mutable counters guarded by its accounting lock."""

    def __init__(self) -> None:
        self.accepted = 0
        self.filtered = 0
        self.delivered = 0
        self.dropped = 0
        self.failed = 0

    def freeze(self) -> EventExporterCounts:
        return EventExporterCounts(
            accepted=self.accepted,
            filtered=self.filtered,
            delivered=self.delivered,
            dropped=self.dropped,
            failed=self.failed,
        )
