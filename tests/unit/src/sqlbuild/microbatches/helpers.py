"""Reusable microbatch projection and SQL test data builders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlbuild.microbatches._helpers.causal_event_identity import producer_completion_event_id
from sqlbuild.microbatches.models import (
    CausalDependencySnapshot,
    ConsumedProducerInterval,
    ConsumerFrontier,
    MicrobatchEvent,
    MicrobatchInterval,
    MicrobatchScope,
    OutstandingProducerCompletions,
    ProducerCompletion,
    ProducerCompletionSnapshot,
)
from sqlbuild.microbatches.types import (
    CausalCompletionKind,
    CausalHistoryStatus,
    MicrobatchCompletionType,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
)

CREATED_AT: datetime = datetime(2026, 1, 1, tzinfo=UTC)
SCOPE: MicrobatchScope = MicrobatchScope(
    scope_kind="direct_logical",
    scope_key="duckdb:main.orders",
    model_name="orders",
    target_database=None,
    target_schema="main",
    target_name="orders",
    physical_generation_id="generation-1",
)
CAUSAL_CREATED_AT: datetime = datetime(2026, 7, 1, tzinfo=UTC)
PRODUCER_SCOPE: MicrobatchScope = MicrobatchScope(
    scope_kind="direct_logical",
    scope_key="duckdb:main.upstream",
    model_name="upstream",
    target_database=None,
    target_schema="main",
    target_name="upstream",
    physical_generation_id="producer-generation-1",
)
CONSUMER_SCOPE: MicrobatchScope = MicrobatchScope(
    scope_kind="direct_logical",
    scope_key="duckdb:main.downstream",
    model_name="downstream",
    target_database=None,
    target_schema="main",
    target_name="downstream",
    physical_generation_id="consumer-generation-1",
)


def completion_event(
    *,
    event_id: str,
    start: str,
    end: str,
    version: str = "F2",
    created_offset: int = 0,
) -> MicrobatchEvent:
    """Build one ordinary integer completion."""

    return MicrobatchEvent(
        event_id=event_id,
        record_type=MicrobatchRecordType.PARTITION_COMPLETION,
        scope=SCOPE,
        origin_run_id="run-1",
        execution_run_id="run-1",
        run_type=MicrobatchRunType.NORMAL,
        completion_type=MicrobatchCompletionType.INITIAL,
        run_start="0",
        run_end="3",
        partition_start=start,
        partition_end=end,
        batch_size="1",
        cursor_column="batch_id",
        cursor_type="integer",
        model_version_hash=version,
        definition_hash="definition",
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        created_at=CREATED_AT + timedelta(seconds=created_offset),
    )


def synthetic_completion_event(*, event_id: str, start: str, end: str) -> MicrobatchEvent:
    """Build one synthetic integer completion with unknown provenance."""

    return MicrobatchEvent(
        event_id=event_id,
        record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
        scope=SCOPE,
        origin_run_id="run-1",
        execution_run_id="run-1",
        run_type=MicrobatchRunType.NORMAL,
        completion_type=MicrobatchCompletionType.INITIAL,
        run_start="0",
        run_end="3",
        partition_start=start,
        partition_end=end,
        batch_size="1",
        cursor_column="batch_id",
        cursor_type="integer",
        model_version_hash=None,
        definition_hash=None,
        fingerprint_status=MicrobatchFingerprintStatus.UNKNOWN,
        created_at=CREATED_AT,
    )


def replay_requirement(*, required_version: str = "F2") -> MicrobatchEvent:
    """Build one bounded replay requirement."""

    return MicrobatchEvent(
        event_id="requirement",
        record_type=MicrobatchRecordType.REPLAY_REQUIREMENT,
        scope=SCOPE,
        origin_run_id="replay-run",
        execution_run_id="replay-run",
        run_type=MicrobatchRunType.REPLAY_ON_CHANGE,
        run_start="0",
        run_end="3",
        batch_size="1",
        cursor_column="batch_id",
        cursor_type="integer",
        model_version_hash=required_version,
        definition_hash="definition",
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        replay_requirement_id="replay-F2",
        required_model_version_hash=required_version,
        previous_model_version_hash="F1",
    )


def expected_integer_intervals() -> tuple[MicrobatchInterval, ...]:
    """Return three canonical integer partitions."""

    return tuple(MicrobatchInterval(start=str(index), end=str(index + 1)) for index in range(3))


def timestamp_completion(
    *, event_id: str, start: str, end: str, version: str, offset: int
) -> MicrobatchEvent:
    """Build one timestamp completion for overlap projection tests."""

    scope: MicrobatchScope = MicrobatchScope(
        scope_kind="direct_logical",
        scope_key="duckdb:main.events",
        model_name="events",
        target_database=None,
        target_schema="main",
        target_name="events",
        physical_generation_id="generation-1",
    )
    return MicrobatchEvent(
        event_id=event_id,
        record_type=MicrobatchRecordType.PARTITION_COMPLETION,
        scope=scope,
        origin_run_id="run",
        execution_run_id="run",
        run_type=MicrobatchRunType.NORMAL,
        completion_type=MicrobatchCompletionType.INITIAL,
        run_start="2026-01-01T00:00:00",
        run_end="2026-01-01T04:00:00",
        partition_start=start,
        partition_end=end,
        batch_size="2h",
        cursor_column="event_time",
        cursor_type="timestamp",
        model_version_hash=version,
        definition_hash=version,
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        created_at=CREATED_AT + timedelta(seconds=offset),
    )


def completion_for_sql() -> MicrobatchEvent:
    """Build a completion containing values useful for SQL encoding assertions."""

    return MicrobatchEvent(
        event_id="event-1",
        record_type=MicrobatchRecordType.PARTITION_COMPLETION,
        scope=MicrobatchScope(
            scope_kind="direct_logical",
            scope_key="duckdb:analytics.orders",
            model_name="orders",
            target_database=None,
            target_schema="analytics",
            target_name="orders",
            physical_generation_id="*",
        ),
        origin_run_id="origin-run",
        execution_run_id="execution-run",
        run_type=MicrobatchRunType.REPLAY_ON_CHANGE,
        completion_type=MicrobatchCompletionType.RECOVERY,
        run_start="0",
        run_end="1",
        partition_start="0",
        partition_end="1",
        batch_size="1",
        cursor_column="batch_id",
        cursor_type="integer",
        model_version_hash="F2",
        definition_hash="fingerprint'definition",
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        rows_affected=0,
        created_at=datetime(2026, 1, 1),
    )


def causal_completion(
    *, event_id: str, start: str, end: str, created_at: datetime = CAUSAL_CREATED_AT
) -> ProducerCompletion:
    return ProducerCompletion(
        event_id=event_id,
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
        interval=MicrobatchInterval(start=start, end=end),
        producer_run_id=f"run-{event_id}",
        run_type=MicrobatchRunType.NORMAL,
        completion_kind=CausalCompletionKind.PHYSICAL,
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        created_at=created_at,
    )


def causal_frontier(
    *,
    captured: frozenset[str],
    event_id: str,
    consumed: tuple[ConsumedProducerInterval, ...] = (),
) -> ConsumerFrontier:
    return ConsumerFrontier(
        event_id=event_id,
        consumer_scope=CONSUMER_SCOPE,
        consumer_model_version_hash="consumer-v1",
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
        captured_producer_event_ids=captured,
        consumer_run_id="consumer-run",
        consumed_intervals=consumed,
        created_at=CAUSAL_CREATED_AT,
    )


def causal_completion_id(*, producer_run_id: str) -> str:
    return producer_completion_event_id(
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
        interval_start="2026-07-01",
        interval_end="2026-08-01",
        producer_run_id=producer_run_id,
        completion_kind=CausalCompletionKind.PHYSICAL,
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
    )


def causal_dependency(
    *, history_status: CausalHistoryStatus, intervals: tuple[MicrobatchInterval, ...]
) -> CausalDependencySnapshot:
    snapshot: ProducerCompletionSnapshot = ProducerCompletionSnapshot(
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
        completions=(),
        event_ids=frozenset(),
    )
    return CausalDependencySnapshot(
        producer_model_name="upstream",
        producer_cursor_grain="month",
        history_status=history_status,
        outstanding=OutstandingProducerCompletions(
            snapshot=snapshot,
            acknowledged_event_ids=frozenset(),
            completions=(),
            intervals=intervals,
        ),
    )
