"""Set-based causal projections for producer completions and consumer frontiers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import (
    ConsumerFrontier,
    MicrobatchInterval,
    MicrobatchScope,
    OutstandingProducerCompletions,
    ProducerCompletion,
    ProducerCompletionSnapshot,
)


def snapshot_producer_completions(
    *,
    completions: tuple[ProducerCompletion, ...],
    producer_scope: MicrobatchScope,
    producer_model_version_hash: str | None,
) -> ProducerCompletionSnapshot:
    """Capture IDs for one exact producer physical generation and model version."""

    selected: tuple[ProducerCompletion, ...] = tuple(
        sorted(
            (
                completion
                for completion in completions
                if completion.producer_scope == producer_scope
                and completion.producer_model_version_hash == producer_model_version_hash
            ),
            key=lambda completion: completion.event_id,
        )
    )
    return ProducerCompletionSnapshot(
        producer_scope=producer_scope,
        producer_model_version_hash=producer_model_version_hash,
        completions=selected,
        event_ids=frozenset(completion.event_id for completion in selected),
    )


def project_outstanding_producer_completions(
    *,
    snapshot: ProducerCompletionSnapshot,
    frontiers: tuple[ConsumerFrontier, ...],
    consumer_scope: MicrobatchScope,
    consumer_model_version_hash: str | None,
    cursor_type: str,
) -> OutstandingProducerCompletions:
    """Subtract exact acknowledgements without using event timestamps as causality."""

    acknowledged: frozenset[str] = frozenset().union(
        *(
            frontier.captured_producer_event_ids
            for frontier in frontiers
            if frontier.consumer_scope == consumer_scope
            and frontier.consumer_model_version_hash == consumer_model_version_hash
            and frontier.producer_scope == snapshot.producer_scope
            and frontier.producer_model_version_hash == snapshot.producer_model_version_hash
        )
    )
    consumed_by_event: dict[str, list[MicrobatchInterval]] = {}
    for frontier in frontiers:
        if (
            frontier.consumer_scope != consumer_scope
            or frontier.consumer_model_version_hash != consumer_model_version_hash
            or frontier.producer_scope != snapshot.producer_scope
            or frontier.producer_model_version_hash != snapshot.producer_model_version_hash
        ):
            continue
        for consumed in frontier.consumed_intervals:
            consumed_by_event.setdefault(consumed.producer_event_id, []).append(consumed.interval)
    outstanding_values: list[ProducerCompletion] = []
    for completion in snapshot.completions:
        if completion.event_id in acknowledged:
            continue
        remaining: tuple[MicrobatchInterval, ...] = _subtract_intervals(
            interval=completion.interval,
            consumed=tuple(consumed_by_event.get(completion.event_id, ())),
            cursor_type=cursor_type,
        )
        outstanding_values.extend(
            ProducerCompletion(
                event_id=completion.event_id,
                producer_scope=completion.producer_scope,
                producer_model_version_hash=completion.producer_model_version_hash,
                interval=interval,
                producer_run_id=completion.producer_run_id,
                run_type=completion.run_type,
                completion_kind=completion.completion_kind,
                fingerprint_status=completion.fingerprint_status,
                created_at=completion.created_at,
            )
            for interval in remaining
        )
    outstanding: tuple[ProducerCompletion, ...] = tuple(outstanding_values)
    return OutstandingProducerCompletions(
        snapshot=snapshot,
        acknowledged_event_ids=acknowledged,
        completions=outstanding,
        intervals=merge_causal_intervals(
            intervals=tuple(completion.interval for completion in outstanding),
            cursor_type=cursor_type,
        ),
    )


def _subtract_intervals(
    *, interval: MicrobatchInterval, consumed: tuple[MicrobatchInterval, ...], cursor_type: str
) -> tuple[MicrobatchInterval, ...]:
    remaining: list[MicrobatchInterval] = [interval]
    for used in merge_causal_intervals(intervals=consumed, cursor_type=cursor_type):
        next_remaining: list[MicrobatchInterval] = []
        for candidate in remaining:
            if not _lt(left=candidate.start, right=used.end, cursor_type=cursor_type) or not _lt(
                left=used.start, right=candidate.end, cursor_type=cursor_type
            ):
                next_remaining.append(candidate)
                continue
            if _lt(left=candidate.start, right=used.start, cursor_type=cursor_type):
                next_remaining.append(MicrobatchInterval(candidate.start, used.start))
            if _lt(left=used.end, right=candidate.end, cursor_type=cursor_type):
                next_remaining.append(MicrobatchInterval(used.end, candidate.end))
        remaining = next_remaining
    return tuple(remaining)


def merge_causal_intervals(
    *, intervals: tuple[MicrobatchInterval, ...], cursor_type: str
) -> tuple[MicrobatchInterval, ...]:
    ordered: tuple[MicrobatchInterval, ...] = tuple(
        sorted(
            intervals,
            key=lambda interval: _cursor_value(value=interval.start, cursor_type=cursor_type),
        )
    )
    merged: list[MicrobatchInterval] = []
    for interval in ordered:
        if not merged or _lt(left=merged[-1].end, right=interval.start, cursor_type=cursor_type):
            merged.append(interval)
            continue
        if _lt(left=merged[-1].end, right=interval.end, cursor_type=cursor_type):
            merged[-1] = MicrobatchInterval(start=merged[-1].start, end=interval.end)
    return tuple(merged)


def _cursor_value(*, value: str, cursor_type: str) -> datetime | Decimal:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(value)
    if cursor_type == CursorType.INTEGER:
        return Decimal(value)
    raise MicrobatchStateError(f"unsupported causal cursor type: {cursor_type}")


def _lt(*, left: str, right: str, cursor_type: str) -> bool:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(left) < datetime.fromisoformat(right)
    if cursor_type == CursorType.INTEGER:
        return Decimal(left) < Decimal(right)
    raise MicrobatchStateError(f"unsupported causal cursor type: {cursor_type}")
