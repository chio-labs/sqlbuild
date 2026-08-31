"""Archive lifecycle projection entrypoint pending external integration."""

from sqlbuild.archives._helpers.projection import project_archive_events as _project_archive_events
from sqlbuild.archives.models import ArchiveEvent, ArchiveProjection


def project_archive_events(events: tuple[ArchiveEvent, ...]) -> ArchiveProjection:
    """Project immutable archive facts into current lifecycle state."""

    return _project_archive_events(events)
