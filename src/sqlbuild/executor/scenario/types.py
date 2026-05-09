from enum import StrEnum


class ScenarioSnapshotState(StrEnum):
    """Availability state for one durable local scenario snapshot."""

    FRESH = "fresh"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"
