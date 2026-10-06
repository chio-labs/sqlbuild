"""Type-layer declarations for CLI output."""

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlbuild.compiler.compile.models import CompilerDiagnostic
    from sqlbuild.compiler.planner.models import CursorBounds

type WrittenTargetDiagnostic = CompilerDiagnostic

type PlannedCursorBounds = CursorBounds


class CursorBoundsOwner(StrEnum):
    """Component responsible for resolving effective cursor bounds."""

    PLANNER = "planner"
    RUNTIME = "runtime"


class CursorResolutionStatus(StrEnum):
    """Availability of effective cursor bounds at plan time."""

    DEFERRED = "deferred"
    RESOLVED = "resolved"
    UNAVAILABLE = "unavailable"
    NO_INPUT_ROWS = "no_input_rows"


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
