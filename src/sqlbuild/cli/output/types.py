"""Type-layer declarations for CLI output."""

from enum import StrEnum


class CursorBoundsOwner(StrEnum):
    """Component responsible for resolving effective cursor bounds."""

    PLANNER = "planner"
    RUNTIME = "runtime"


class CursorResolutionStatus(StrEnum):
    """Availability of effective cursor bounds at plan time."""

    DEFERRED = "deferred"
    RESOLVED = "resolved"
    UNAVAILABLE = "unavailable"
