"""Planner-private microbatch range capping and capped-watermark validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.main._cursor_roles import resolve_cursor_input_roles
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompileSqlReference,
)
from sqlbuild.compiler.planner._helpers.resolve.lineage import resolve_lineage_reference
from sqlbuild.compiler.planner.main.execution.microbatch_limit import (
    _resolve_microbatch_limit_config,
)
from sqlbuild.compiler.planner.models import CursorBounds, Duration
from sqlbuild.compiler.planner.types import CursorType, IncrementalMode
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.cursor_algebra.main.cap_from_end import cap_from_end
from sqlbuild.cursor_algebra.main.cap_from_start import cap_from_start
from sqlbuild.cursor_algebra.main.clamp import clamp
from sqlbuild.cursor_algebra.main.merge import merge
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.split_into_batches import split_into_batches
from sqlbuild.cursor_algebra.models import AlignedInterval, IntegerValue
from sqlbuild.cursor_algebra.types import CursorScalar
from sqlbuild.spec.contracts.types import MicrobatchLimitAction

_CAP_ACTIONS: frozenset[MicrobatchLimitAction] = frozenset(
    {MicrobatchLimitAction.CAP_FROM_START, MicrobatchLimitAction.CAP_FROM_END}
)


def cap_microbatch_bounds(
    *,
    bounds: CursorBounds,
    batch_size: str,
    cursor_type: str,
    max_batches: int,
    action: MicrobatchLimitAction,
) -> CursorBounds:
    """Cap one concrete range to its earliest or latest batch windows."""

    if action not in {
        MicrobatchLimitAction.CAP_FROM_END,
        MicrobatchLimitAction.CAP_FROM_START,
    }:
        return bounds
    if cursor_type == CursorType.INTEGER:
        try:
            start: int = int(Decimal(bounds.start))
            end: int = int(Decimal(bounds.end))
            size: int = int(Decimal(batch_size))
        except (InvalidOperation, ValueError, OverflowError):
            return bounds
        if size <= 0:
            return bounds
        capped_start: int = start
        capped_end: int = end
        if action == MicrobatchLimitAction.CAP_FROM_START:
            capped_end = min(end, start + size * max_batches)
        else:
            batch_count: int = max(0, (end - start + size - 1) // size)
            skipped_batches: int = max(0, batch_count - max_batches)
            capped_start = start + size * skipped_batches
        if capped_start >= capped_end:
            if action == MicrobatchLimitAction.CAP_FROM_START:
                return CursorBounds(start=bounds.start, end=str(capped_end))
            return CursorBounds(start=str(capped_start), end=bounds.end)
        start_value: CursorScalar = parse(raw=capped_start, cursor_type=cursor_type)
        end_value: CursorScalar = parse(raw=capped_end, cursor_type=cursor_type)
        if not isinstance(start_value, IntegerValue) or not isinstance(end_value, IntegerValue):
            return bounds
        interval: AlignedInterval = AlignedInterval(start=start_value, end=end_value, grain=None)
        batches: tuple[AlignedInterval, ...] = split_into_batches(
            interval=interval, step=capped_end - capped_start
        )
        if action == MicrobatchLimitAction.CAP_FROM_START:
            selected: tuple[AlignedInterval, ...] = cap_from_start(
                intervals=batches, count=max_batches
            )
            if not selected:
                return bounds
            merged: tuple[AlignedInterval, ...] = merge(intervals=selected)
            capped: AlignedInterval | None = clamp(interval=merged[0], bounds=interval)
            return (
                bounds
                if capped is None
                else CursorBounds(start=bounds.start, end=render(value=capped.end))
            )
        selected = cap_from_end(intervals=batches, count=max_batches)
        if not selected:
            return bounds
        merged = merge(intervals=selected)
        capped = clamp(interval=merged[0], bounds=interval)
        return (
            bounds
            if capped is None
            else CursorBounds(start=render(value=capped.start), end=bounds.end)
        )

    if cursor_type != CursorType.TIMESTAMP:
        return bounds
    duration: Duration | None = Duration.parse(batch_size)
    if duration is None:
        return bounds
    try:
        start_at: datetime = datetime.fromisoformat(bounds.start)
        end_at: datetime = datetime.fromisoformat(bounds.end)
    except (TypeError, ValueError):
        return bounds
    if action == MicrobatchLimitAction.CAP_FROM_START:
        capped_end: datetime = start_at
        for _ in range(max_batches):
            capped_end = min(duration.add_to(capped_end), end_at)
        return CursorBounds(start=bounds.start, end=capped_end.isoformat())
    boundaries: list[datetime] = [start_at]
    while boundaries[-1] < end_at:
        boundaries.append(min(duration.add_to(boundaries[-1]), end_at))
    capped_start: datetime = boundaries[max(0, len(boundaries) - 1 - max_batches)]
    return CursorBounds(start=capped_start.isoformat(), end=bounds.end)


def validate_capped_watermark_inputs(
    *,
    model: CompiledModel,
    models_by_name: dict[str, CompiledModel],
    functions_by_name: dict[str, CompiledFunction] | None = None,
) -> None:
    """Reject capped producers feeding microbatch watermark inputs."""

    if _config_str(model=model, key="incremental_mode") != IncrementalMode.MICROBATCH:
        return
    input_name: str
    for input_name in resolve_cursor_input_roles(model=model).watermark_inputs:
        ref: CompileSqlReference = resolve_lineage_reference(
            model=model,
            input_name=input_name,
            models_by_name=models_by_name,
            functions_by_name=functions_by_name or {},
        )
        producer: CompiledModel | None = _find_capped_producer_ancestor(
            reference=ref,
            models_by_name=models_by_name,
            functions_by_name=functions_by_name or {},
        )
        if producer is None:
            continue
        if producer.name != input_name:
            raise CompileInputError(
                f"model '{model.name}' uses watermark input '{input_name}' derived from capped "
                f"producer '{producer.name}'; capped producers cannot serve as watermark inputs"
            )
        raise CompileInputError(
            f"model '{model.name}' uses capped producer '{producer.name}' as a watermark input; "
            "capped producers cannot serve as watermark inputs"
        )


def _find_capped_producer_ancestor(
    *,
    reference: CompileSqlReference,
    models_by_name: dict[str, CompiledModel],
    functions_by_name: dict[str, CompiledFunction],
) -> CompiledModel | None:
    """Return the first capped microbatch model in a reference's upstream lineage."""

    pending: list[CompileSqlReference] = [reference]
    visited: set[tuple[str, str]] = set()
    while pending:
        current: CompileSqlReference = pending.pop(0)
        identity: tuple[str, str] = (current.ref_kind, current.ref_name)
        if identity in visited:
            continue
        visited.add(identity)
        if current.ref_kind == SqlReferenceKind.REF:
            producer: CompiledModel | None = models_by_name.get(current.ref_name)
            if producer is None:
                continue
            action: MicrobatchLimitAction | None = _resolve_microbatch_limit_config(
                values=producer.config.values
            )[1]
            is_microbatch: bool = (
                _config_str(model=producer, key="incremental_mode") == IncrementalMode.MICROBATCH
            )
            if is_microbatch and action in _CAP_ACTIONS:
                return producer
            if is_microbatch:
                watermark_name: str
                for watermark_name in resolve_cursor_input_roles(model=producer).watermark_inputs:
                    pending.append(
                        resolve_lineage_reference(
                            model=producer,
                            input_name=watermark_name,
                            models_by_name=models_by_name,
                            functions_by_name=functions_by_name,
                        )
                    )
            else:
                pending.extend(producer.references)
        elif current.ref_kind in {
            SqlReferenceKind.UDF,
            SqlReferenceKind.TABLE_FUNCTION,
        }:
            function: CompiledFunction | None = functions_by_name.get(current.ref_name)
            if function is not None:
                pending.extend(function.references)
    return None


def _config_str(*, model: CompiledModel, key: str) -> str | None:
    """Extract a string config value from model config."""

    raw: object | None = model.config.values.get(key)
    return raw if isinstance(raw, str) else None
