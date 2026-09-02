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


class PlanRowKind(StrEnum):
    """Structural classification of a rendered plan line."""

    ENTRY = "entry"
    LEAF = "leaf"
    NESTED = "nested"
    OTHER = "other"


class IntegrationOutputKind(StrEnum):
    """Kind of integration-facing result enrichment."""

    ASSET = "asset"
    CHECK = "check"
