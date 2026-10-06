"""Shared cursor-plan projection for text and JSON output."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.cli.output.models import CursorPlanDetails
from sqlbuild.cli.output.types import CursorBoundsOwner, CursorResolutionStatus
from sqlbuild.compiler.planner.main.execution.aligned_timestamp_bounds import (
    aligned_timestamp_bounds,
)
from sqlbuild.compiler.planner.main.execution.effective_microbatch_batch_size import (
    resolve_effective_microbatch_batch_size,
)
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputRelation,
    Duration,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    CursorGrain,
    CursorType,
    IncrementalMode,
    MicrobatchStrategy,
)
from sqlbuild.cursor_algebra.constants import GRAIN_ORDER
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import BoundSentinel
from sqlbuild.spec.contracts.constants import EFFECTIVE_BATCH_SIZE_TOKEN


def build_cursor_plan_details(*, entry: ModelPlanEntry) -> CursorPlanDetails | None:
    """Project one model entry into stable cursor details for operator output."""

    if entry.cursor_column is None:
        return None
    runtime_owned: bool = any(
        relation.is_runtime_owned for relation in entry.cursor_input_relations
    ) and not (entry.start_cursor_override is not None and entry.end_cursor_override is not None)
    resolved_bounds: CursorBounds | None = entry.microbatch_range or entry.cursor_bounds
    if resolved_bounds is not None and (
        isinstance(resolved_bounds.start, BoundSentinel)
        or isinstance(resolved_bounds.end, BoundSentinel)
    ):
        resolved_bounds = None
    effective_grain: str | None = _effective_grain(entry=entry)
    effective_batch_size: str | None = _effective_batch_size(
        entry=entry, effective_grain=effective_grain
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
    if entry.empty_cursor_inputs:
        resolution_status: CursorResolutionStatus = CursorResolutionStatus.NO_INPUT_ROWS
    elif resolved_bounds is not None:
        resolution_status = CursorResolutionStatus.RESOLVED
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
        empty_inputs=entry.empty_cursor_inputs,
        waiting_on_empty_inputs=entry.waiting_on_empty_inputs,
    )


def _effective_grain(*, entry: ModelPlanEntry) -> str | None:
    """Return the coarsest timestamp grain declared across a model and its inputs."""

    if entry.cursor_type != CursorType.TIMESTAMP:
        return entry.cursor_grain
    effective: str = entry.cursor_grain or CursorGrain.SECOND
    if entry.microbatch_strategy == MicrobatchStrategy.WATERMARK:
        return effective
    for relation in entry.cursor_input_relations:
        relation_grain: str = relation.cursor_grain or CursorGrain.SECOND
        if GRAIN_ORDER[CursorGrain(relation_grain)] > GRAIN_ORDER[CursorGrain(effective)]:
            effective = relation_grain
    return effective


def _effective_batch_size(*, entry: ModelPlanEntry, effective_grain: str | None) -> str | None:
    """Return the batch size the current executor path will apply."""

    batch_size: str | None = entry.batch_size
    if batch_size is None or effective_grain is None:
        return batch_size
    return resolve_effective_microbatch_batch_size(
        batch_size=batch_size,
        effective_grain=effective_grain,
    )


def _count_batches(*, bounds: CursorBounds, batch_size: str, cursor_type: str) -> int | None:
    """Count the windows the executor will create without materializing them."""

    if cursor_type == CursorType.TIMESTAMP:
        duration: Duration | None = Duration.parse(batch_size)
        if duration is None:
            return None
        if not isinstance(bounds.start, DateValue | TimestampValue) or not isinstance(
            bounds.end, DateValue | TimestampValue
        ):
            return None
        current: datetime
        end: datetime
        current, end = aligned_timestamp_bounds(start=bounds.start, end=bounds.end)
        count: int = 0
        while current < end:
            current = min(duration.add_to(current), end)
            count += 1
        return count
    if cursor_type == CursorType.INTEGER:
        if not isinstance(bounds.start, IntegerValue) or not isinstance(bounds.end, IntegerValue):
            return None
        start: int = bounds.start.value
        end: int = bounds.end.value
        try:
            size: int = int(batch_size)
        except ValueError:
            return None
        if size <= 0 or start >= end:
            return 0
        return (end - start + size - 1) // size
    return None


def runtime_cursor_inputs_clause(*, entry: ModelPlanEntry) -> str:
    """Name the cursor inputs this run brings up to date before the model's range is known."""

    labels: list[str] = []
    relation: CursorInputRelation
    for relation in entry.cursor_input_relations:
        if not relation.is_runtime_owned:
            continue
        name: str = relation.input_name or relation.relation
        label: str = (
            f"{relation.input_kind.value} {name}" if relation.input_kind is not None else name
        )
        if label not in labels:
            labels.append(label)
    if not labels:
        return "once its inputs are up to date"
    if len(labels) == 1:
        return f"once {labels[0]} is up to date"
    return f"once {', '.join(labels[:-1])} and {labels[-1]} are up to date"


def append_microbatch_plan_detail(
    *, lines: list[str], details: CursorPlanDetails, entry: ModelPlanEntry
) -> list[str]:
    """Append grain, batch size, and known-or-deferred batch count."""

    if details.declared_grain is not None:
        grain_text: str = details.declared_grain
        resolved_grain: str = details.effective_grain or details.declared_grain
        if resolved_grain != details.declared_grain:
            grain_text = f"{details.declared_grain} -> {resolved_grain} (effective)"
        lines.append(f"    grain: {grain_text}")
    if details.declared_batch_size is not None:
        batch_size_text: str = details.declared_batch_size
        if details.declared_batch_size == EFFECTIVE_BATCH_SIZE_TOKEN:
            resolved_batch_size: str = details.effective_batch_size or "runtime"
            batch_size_text = (
                resolved_batch_size
                if details.effective_grain == details.declared_grain
                else f"{details.declared_batch_size} -> {resolved_batch_size}"
            )
        lines.append(f"    batch size: {batch_size_text}")
    if details.planned_batch_count is not None and details.effective_batch_size is not None:
        lines.append(f"    batches: {details.planned_batch_count} x {details.effective_batch_size}")
    if details.resolution_status == CursorResolutionStatus.DEFERRED:
        lines.append(
            f"    batches: counted at run time, {runtime_cursor_inputs_clause(entry=entry)}"
        )
    lines.append(f"    batch concurrency: {entry.batch_concurrency}")
    if entry.unaccounted_partition_policy is not None:
        lines.append(f"    unaccounted partition policy: {entry.unaccounted_partition_policy}")
    return lines
