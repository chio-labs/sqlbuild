"""Shared cursor-plan projection for text and JSON output."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.cli.output.models import CursorPlanDetails
from sqlbuild.cli.output.types import CursorBoundsOwner, CursorResolutionStatus
from sqlbuild.compiler.planner.models import CursorBounds, Duration, ModelPlanEntry
from sqlbuild.compiler.planner.types import CursorGrain, CursorType, IncrementalMode

_GRAIN_ORDER: dict[str, int] = {
    CursorGrain.SECOND: 0,
    CursorGrain.MINUTE: 1,
    CursorGrain.HOUR: 2,
    CursorGrain.DAY: 3,
    CursorGrain.MONTH: 4,
    CursorGrain.YEAR: 5,
}
_GRAIN_BATCH_SIZE: dict[str, str] = {
    CursorGrain.SECOND: "1s",
    CursorGrain.MINUTE: "1m",
    CursorGrain.HOUR: "1h",
    CursorGrain.DAY: "1d",
    CursorGrain.MONTH: "1mo",
    CursorGrain.YEAR: "1y",
}


def build_cursor_plan_details(*, entry: ModelPlanEntry) -> CursorPlanDetails | None:
    """Project one model entry into stable cursor details for operator output."""

    if entry.cursor_column is None:
        return None
    runtime_owned: bool = any(relation.is_model_backed for relation in entry.cursor_input_relations)
    resolved_bounds: CursorBounds | None = entry.microbatch_range or entry.cursor_bounds
    effective_grain: str | None = _effective_grain(entry=entry)
    effective_batch_size: str | None = _effective_batch_size(
        entry=entry,
        runtime_owned=runtime_owned,
        effective_grain=effective_grain,
    )
    planned_batch_count: int | None = None
    if (
        entry.incremental_mode == IncrementalMode.MICROBATCH
        and resolved_bounds is not None
        and effective_batch_size is not None
        and entry.cursor_type is not None
    ):
        planned_batch_count = _count_batches(
            bounds=resolved_bounds,
            batch_size=effective_batch_size,
            cursor_type=entry.cursor_type,
        )
    if resolved_bounds is not None:
        resolution_status: CursorResolutionStatus = CursorResolutionStatus.RESOLVED
    elif runtime_owned:
        resolution_status = CursorResolutionStatus.DEFERRED
    else:
        resolution_status = CursorResolutionStatus.UNAVAILABLE
    return CursorPlanDetails(
        requested_start=entry.start_cursor_override,
        requested_end=entry.end_cursor_override,
        bounds_owner=(CursorBoundsOwner.RUNTIME if runtime_owned else CursorBoundsOwner.PLANNER),
        resolution_status=resolution_status,
        resolved_bounds=resolved_bounds,
        declared_grain=entry.cursor_grain,
        effective_grain=effective_grain,
        declared_batch_size=entry.batch_size,
        effective_batch_size=effective_batch_size,
        planned_batch_count=planned_batch_count,
    )


def _effective_grain(*, entry: ModelPlanEntry) -> str | None:
    """Return the coarsest timestamp grain declared across a model and its inputs."""

    if entry.cursor_type != CursorType.TIMESTAMP:
        return entry.cursor_grain
    effective: str = entry.cursor_grain or CursorGrain.SECOND
    for relation in entry.cursor_input_relations:
        relation_grain: str = relation.cursor_grain or CursorGrain.SECOND
        if _GRAIN_ORDER[relation_grain] > _GRAIN_ORDER[effective]:
            effective = relation_grain
    return effective


def _effective_batch_size(
    *, entry: ModelPlanEntry, runtime_owned: bool, effective_grain: str | None
) -> str | None:
    """Return the batch size the current executor path will apply."""

    batch_size: str | None = entry.batch_size
    if not runtime_owned or batch_size is None or effective_grain is None:
        return batch_size
    batch_order: int | None = _batch_size_order(batch_size=batch_size)
    if batch_order is None or batch_order >= _GRAIN_ORDER[effective_grain]:
        return batch_size
    return _GRAIN_BATCH_SIZE[effective_grain]


def _batch_size_order(*, batch_size: str) -> int | None:
    """Map a timestamp duration suffix to its cursor-grain order."""

    if batch_size.endswith("y") and not batch_size.endswith("dy"):
        return 5
    if batch_size.endswith("mo"):
        return 4
    if batch_size.endswith("d"):
        return 3
    if batch_size.endswith("h"):
        return 2
    if batch_size.endswith("m"):
        return 1
    if batch_size.endswith("s"):
        return 0
    return None


def _count_batches(*, bounds: CursorBounds, batch_size: str, cursor_type: str) -> int | None:
    """Count the windows the executor will create without materializing them."""

    if cursor_type == CursorType.TIMESTAMP:
        duration: Duration | None = Duration.parse(batch_size)
        if duration is None:
            return None
        try:
            current: datetime = datetime.fromisoformat(bounds.start)
            end: datetime = datetime.fromisoformat(bounds.end)
        except (TypeError, ValueError):
            return None
        count: int = 0
        while current < end:
            current = min(duration.add_to(current), end)
            count += 1
        return count
    if cursor_type == CursorType.INTEGER:
        try:
            start: int = int(Decimal(bounds.start))
            end = int(Decimal(bounds.end))
            size: int = int(Decimal(batch_size))
        except (InvalidOperation, ValueError, OverflowError):
            return None
        if size <= 0 or start >= end:
            return 0
        return (end - start + size - 1) // size
    return None
