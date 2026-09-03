"""Capture one stable causal dependency snapshot from durable event history."""

from __future__ import annotations

from sqlbuild.microbatches._helpers.causal_projection import (
    project_outstanding_producer_completions,
    snapshot_producer_completions,
)
from sqlbuild.microbatches.classes.causal_event_store import CausalMicrobatchEventStore
from sqlbuild.microbatches.main.physical_causal_completion import physical_producer_completion
from sqlbuild.microbatches.models import (
    CausalDependencySnapshot,
    ConsumerFrontier,
    MicrobatchEvent,
    MicrobatchInterval,
    MicrobatchScope,
    OutstandingProducerCompletions,
    ProducerCompletion,
    ProducerCompletionSnapshot,
)
from sqlbuild.microbatches.types import (
    CausalHistoryStatus,
    MicrobatchEventStore,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
)


def capture_causal_dependency(
    *,
    producer_store: MicrobatchEventStore,
    consumer_store: MicrobatchEventStore,
    producer_scope: MicrobatchScope,
    producer_model_version_hash: str | None,
    producer_model_name: str,
    producer_cursor_grain: str | None,
    consumer_scope: MicrobatchScope,
    consumer_model_version_hash: str | None,
    cursor_type: str,
) -> CausalDependencySnapshot:
    """Capture producer IDs after readiness and project exact outstanding work."""

    causal_store: CausalMicrobatchEventStore = CausalMicrobatchEventStore(producer_store)
    producer_records: tuple[ProducerCompletion, ...] = causal_store.read_producer_completions(
        producer_scope
    )
    physical_history: tuple[MicrobatchEvent, ...] = producer_store.read_scope_history(
        producer_scope
    )
    known_ids: frozenset[str] = frozenset(record.event_id for record in producer_records)
    recovered: tuple[ProducerCompletion, ...] = tuple(
        completion
        for event in physical_history
        if event.record_type == MicrobatchRecordType.PARTITION_COMPLETION
        and event.fingerprint_status == MicrobatchFingerprintStatus.KNOWN
        and event.partition_start is not None
        and event.partition_end is not None
        and event.partition_start != event.partition_end
        and (
            completion := physical_producer_completion(
                scope=event.scope,
                model_version_hash=event.model_version_hash,
                interval=MicrobatchInterval(event.partition_start, event.partition_end),
                run_id=event.execution_run_id,
                run_type=event.run_type,
                created_at=event.completed_at or event.created_at,
            )
        ).event_id
        not in known_ids
    )
    if recovered:
        causal_store.write_many(recovered)
        producer_records = (*producer_records, *recovered)
    snapshot: ProducerCompletionSnapshot = snapshot_producer_completions(
        completions=producer_records,
        producer_scope=producer_scope,
        producer_model_version_hash=producer_model_version_hash,
    )
    frontiers: tuple[ConsumerFrontier, ...] = CausalMicrobatchEventStore(
        consumer_store
    ).read_consumer_frontiers(consumer_scope)
    outstanding: OutstandingProducerCompletions = project_outstanding_producer_completions(
        snapshot=snapshot,
        frontiers=frontiers,
        consumer_scope=consumer_scope,
        consumer_model_version_hash=consumer_model_version_hash,
        cursor_type=cursor_type,
    )
    known: bool = bool(snapshot.completions) and all(
        completion.fingerprint_status == MicrobatchFingerprintStatus.KNOWN
        for completion in snapshot.completions
    )
    return CausalDependencySnapshot(
        producer_model_name=producer_model_name,
        producer_cursor_grain=producer_cursor_grain,
        history_status=(CausalHistoryStatus.KNOWN if known else CausalHistoryStatus.UNKNOWN),
        outstanding=outstanding,
    )
