"""Structured values shared by CLI output renderers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.output.types import CursorBoundsOwner, CursorResolutionStatus
from sqlbuild.compiler.planner.models import CursorBounds


@dataclass(frozen=True)
class CursorPlanDetails:
    """Operator-facing cursor details shared by plan renderers."""

    requested_start: str | None
    requested_end: str | None
    bounds_owner: CursorBoundsOwner
    resolution_status: CursorResolutionStatus
    resolved_bounds: CursorBounds | None
    declared_grain: str | None
    effective_grain: str | None
    declared_batch_size: str | None
    effective_batch_size: str | None
    planned_batch_count: int | None
