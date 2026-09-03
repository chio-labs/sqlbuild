"""Publish model-terminal producer completion and consumer frontier facts."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.microbatches._helpers.causal_event_identity import (
    consumer_frontier_event_id,
    producer_completion_event_id,
)
from sqlbuild.microbatches.classes.causal_event_store import CausalMicrobatchEventStore
from sqlbuild.microbatches.models import (
    CausalDependencySnapshot,
    CausalPublicationResult,
    ConsumedProducerInterval,
    ConsumerFrontier,
    MicrobatchInterval,
    MicrobatchScope,
    ProducerCompletion,
    ProducerCompletionSnapshot,
)
from sqlbuild.microbatches.types import (
    CausalCompletionKind,
    MicrobatchEventStore,
    MicrobatchFingerprintStatus,
    MicrobatchRunType,
)


def publish_terminal_causal_facts(
    *,
    store: MicrobatchEventStore,
    model_scope: MicrobatchScope,
    model_version_hash: str | None,
    run_id: str,
    run_type: MicrobatchRunType,
    completed_intervals: tuple[MicrobatchInterval, ...],
    dependencies: tuple[CausalDependencySnapshot, ...],
    publish_producer_completions: bool = False,
) -> CausalPublicationResult:
    """Publish promoted full-refresh completions and exact consumer interval facts."""

    created_at: datetime = datetime.now(tz=UTC)
    producers: list[ProducerCompletion] = []
    if publish_producer_completions:
        for interval in completed_intervals:
            producer_id: str = producer_completion_event_id(
                producer_scope=model_scope,
                producer_model_version_hash=model_version_hash,
                interval_start=interval.start,
                interval_end=interval.end,
                producer_run_id=run_id,
                completion_kind=CausalCompletionKind.PHYSICAL,
                fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
            )
            producers.append(
                ProducerCompletion(
                    event_id=producer_id,
                    producer_scope=model_scope,
                    producer_model_version_hash=model_version_hash,
                    interval=interval,
                    producer_run_id=run_id,
                    run_type=run_type,
                    completion_kind=CausalCompletionKind.PHYSICAL,
                    fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
                    created_at=created_at,
                )
            )
    frontiers: list[ConsumerFrontier] = []
    for dependency in dependencies:
        snapshot: ProducerCompletionSnapshot = dependency.outstanding.snapshot
        consumed: tuple[ConsumedProducerInterval, ...] = _consumed_intervals(
            dependency=dependency,
            completed_intervals=completed_intervals,
        )
        if not consumed:
            continue
        consumed_ids: frozenset[str] = frozenset()
        frontier_id: str = consumer_frontier_event_id(
            consumer_scope=model_scope,
            consumer_model_version_hash=model_version_hash,
            producer_scope=snapshot.producer_scope,
            producer_model_version_hash=snapshot.producer_model_version_hash,
            captured_producer_event_ids=consumed_ids,
            consumer_run_id=run_id,
            consumed_intervals=consumed,
        )
        frontiers.append(
            ConsumerFrontier(
                event_id=frontier_id,
                consumer_scope=model_scope,
                consumer_model_version_hash=model_version_hash,
                producer_scope=snapshot.producer_scope,
                producer_model_version_hash=snapshot.producer_model_version_hash,
                captured_producer_event_ids=consumed_ids,
                consumer_run_id=run_id,
                consumed_intervals=consumed,
                created_at=created_at,
            )
        )
    CausalMicrobatchEventStore(store).write_many((*producers, *frontiers))
    return CausalPublicationResult(
        producer_completion_event_ids=tuple(producer.event_id for producer in producers),
        consumer_frontier_event_ids=tuple(frontier.event_id for frontier in frontiers),
    )


def _consumed_intervals(
    *,
    dependency: CausalDependencySnapshot,
    completed_intervals: tuple[MicrobatchInterval, ...],
) -> tuple[ConsumedProducerInterval, ...]:
    consumed: list[ConsumedProducerInterval] = []
    for completion in dependency.outstanding.completions:
        for applied in completed_intervals:
            intersection: MicrobatchInterval | None = _intersection(
                left=completion.interval, right=applied
            )
            if intersection is not None:
                consumed.append(
                    ConsumedProducerInterval(
                        producer_event_id=completion.event_id,
                        interval=intersection,
                    )
                )
    return tuple(consumed)


def _intersection(
    *, left: MicrobatchInterval, right: MicrobatchInterval
) -> MicrobatchInterval | None:
    try:
        decimal_starts: tuple[tuple[Decimal, str], ...] = tuple(
            (Decimal(value), value) for value in (left.start, right.start)
        )
        decimal_ends: tuple[tuple[Decimal, str], ...] = tuple(
            (Decimal(value), value) for value in (left.end, right.end)
        )
        decimal_start, start = max(decimal_starts)
        decimal_end, end = min(decimal_ends)
        return MicrobatchInterval(start, end) if decimal_start < decimal_end else None
    except InvalidOperation:
        timestamp_starts: tuple[tuple[datetime, str], ...] = tuple(
            (datetime.fromisoformat(value), value) for value in (left.start, right.start)
        )
        timestamp_ends: tuple[tuple[datetime, str], ...] = tuple(
            (datetime.fromisoformat(value), value) for value in (left.end, right.end)
        )
        timestamp_start, start = max(timestamp_starts)
        timestamp_end, end = min(timestamp_ends)
        return MicrobatchInterval(start, end) if timestamp_start < timestamp_end else None
