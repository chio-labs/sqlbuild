"""Archive event enums."""

from enum import StrEnum


class ArchiveRecordType(StrEnum):
    """Immutable facts in one archive lifecycle."""

    REQUIREMENT = "requirement"
    COMPLETION = "completion"
    SYNTHETIC_COMPLETION = "synthetic_completion"
    DELETE_REQUIREMENT = "delete_requirement"
    DELETE_COMPLETION = "delete_completion"


class ArchiveProvenanceStatus(StrEnum):
    """How strongly an archive event proves its origin."""

    KNOWN = "known"
    UNKNOWN = "unknown"
