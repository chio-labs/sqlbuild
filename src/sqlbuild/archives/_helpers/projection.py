"""Project append-only archive facts into a current lifecycle."""

from __future__ import annotations

from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.models import ArchiveEvent, ArchiveProjection
from sqlbuild.archives.types import ArchiveRecordType


def project_archive_events(events: tuple[ArchiveEvent, ...]) -> ArchiveProjection:
    """Derive one archive lifecycle while rejecting conflicting duplicate facts."""

    unique_events: dict[str, ArchiveEvent] = {}
    for event in events:
        previous: ArchiveEvent | None = unique_events.get(event.event_id)
        if previous is not None and previous != event:
            raise ArchiveStateError(f"Archive event {event.event_id!r} has conflicting payloads")
        unique_events[event.event_id] = event
    ordered: tuple[ArchiveEvent, ...] = tuple(
        sorted(unique_events.values(), key=lambda event: (event.created_at, event.event_id))
    )
    requirement_ids: set[str] = {event.requirement_id for event in ordered}
    if len(requirement_ids) > 1:
        raise ArchiveStateError("Archive projection received more than one requirement lifecycle")
    return ArchiveProjection(
        requirement=_latest(events=ordered, record_types=(ArchiveRecordType.REQUIREMENT,)),
        completion=_latest(
            events=ordered,
            record_types=(
                ArchiveRecordType.COMPLETION,
                ArchiveRecordType.SYNTHETIC_COMPLETION,
            ),
        ),
        delete_requirement=_latest(
            events=ordered,
            record_types=(ArchiveRecordType.DELETE_REQUIREMENT,),
        ),
        delete_completion=_latest(
            events=ordered,
            record_types=(ArchiveRecordType.DELETE_COMPLETION,),
        ),
    )


def _latest(
    *, events: tuple[ArchiveEvent, ...], record_types: tuple[ArchiveRecordType, ...]
) -> ArchiveEvent | None:
    matches: tuple[ArchiveEvent, ...] = tuple(
        event for event in events if event.record_type in record_types
    )
    return matches[-1] if matches else None
