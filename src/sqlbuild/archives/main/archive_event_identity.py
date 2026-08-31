"""Public deterministic archive event identity entrypoint."""

from sqlbuild.archives._helpers.identity import archive_event_id
from sqlbuild.archives.types import ArchiveRecordType


def build_archive_event_id(*, requirement_id: str, record_type: ArchiveRecordType) -> str:
    """Build one deterministic archive event identity."""

    return archive_event_id(requirement_id=requirement_id, record_type=record_type)
