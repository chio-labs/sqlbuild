"""Logical models for append-only microbatch state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlbuild.microbatches.types import (
    CausalCompletionKind,
    CausalHistoryStatus,
    MicrobatchCompletionType,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
    ReplayRequirementState,
    UnaccountedPartitionPolicy,
)


@dataclass(frozen=True)
class MicrobatchScope:
    """Stable identity for one physical destination generation."""

    scope_kind: str
    scope_key: str
    model_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str
    physical_generation_id: str
    virtual_environment_name: str | None = None
    virtual_model_version_hash: str | None = None


@dataclass(frozen=True)
class MicrobatchEvent:
    """One immutable completion, replay requirement, or synthetic fact."""

    event_id: str
    record_type: MicrobatchRecordType
    scope: MicrobatchScope
    origin_run_id: str
    execution_run_id: str
    run_type: MicrobatchRunType
    run_start: str
    run_end: str
    batch_size: str
    cursor_column: str
    cursor_type: str
    model_version_hash: str | None
    definition_hash: str | None
    fingerprint_status: MicrobatchFingerprintStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    origin_run_started_at: datetime | None = None
    execution_run_started_at: datetime | None = None
    cursor_grain: str | None = None
    completion_type: MicrobatchCompletionType | None = None
    partition_start: str | None = None
    partition_end: str | None = None
    replay_requirement_id: str | None = None
    required_model_version_hash: str | None = None
    previous_model_version_hash: str | None = None
    replay_policy: str | None = None
    rows_affected: int | None = None
    completed_at: datetime | None = None
    coverage_source: str | None = None
    observed_row_count: int | None = None
    observed_at: datetime | None = None
    synthetic_reason: str | None = None
    unaccounted_policy: UnaccountedPartitionPolicy | None = None


@dataclass(frozen=True)
class MicrobatchWriteResult:
    """Counts from one idempotent bulk event publication."""

    total: int
    inserted: int
    already_existing: int


@dataclass(frozen=True)
class MicrobatchInterval:
    """Canonical half-open cursor interval."""

    start: str
    end: str


@dataclass(frozen=True)
class ProducerCompletion:
    """One terminally successful producer interval in one physical generation."""

    event_id: str
    producer_scope: MicrobatchScope
    producer_model_version_hash: str | None
    interval: MicrobatchInterval
    producer_run_id: str
    run_type: MicrobatchRunType
    completion_kind: CausalCompletionKind
    fingerprint_status: MicrobatchFingerprintStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass(frozen=True)
class ConsumerFrontier:
    """Immutable acknowledgement of producer events observed by a consumer."""

    event_id: str
    consumer_scope: MicrobatchScope
    consumer_model_version_hash: str | None
    producer_scope: MicrobatchScope
    producer_model_version_hash: str | None
    captured_producer_event_ids: frozenset[str]
    consumer_run_id: str
    consumed_intervals: tuple[ConsumedProducerInterval, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass(frozen=True)
class ConsumedProducerInterval:
    """Exact portion of one producer event durably consumed by a model run."""

    producer_event_id: str
    interval: MicrobatchInterval


@dataclass(frozen=True)
class ProducerCompletionSnapshot:
    """Stable producer event-ID set for one exact physical generation."""

    producer_scope: MicrobatchScope
    producer_model_version_hash: str | None
    completions: tuple[ProducerCompletion, ...]
    event_ids: frozenset[str]


@dataclass(frozen=True)
class OutstandingProducerCompletions:
    """Producer completions not acknowledged by matching consumer frontiers."""

    snapshot: ProducerCompletionSnapshot
    acknowledged_event_ids: frozenset[str]
    completions: tuple[ProducerCompletion, ...]
    intervals: tuple[MicrobatchInterval, ...]


@dataclass(frozen=True)
class CausalDependencySnapshot:
    """Captured causal state for one cursor-aware producer dependency."""

    producer_model_name: str
    producer_cursor_grain: str | None
    history_status: CausalHistoryStatus
    outstanding: OutstandingProducerCompletions


@dataclass(frozen=True)
class CausalPublicationResult:
    """Causal event IDs durably published at model-terminal success."""

    producer_completion_event_ids: tuple[str, ...] = ()
    consumer_frontier_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectedMicrobatchInterval(MicrobatchInterval):
    """Latest accounting and fingerprint provenance for an interval."""

    fingerprint_status: MicrobatchFingerprintStatus
    model_version_hash: str | None
    record_type: MicrobatchRecordType
    completion_type: MicrobatchCompletionType | None
    event_id: str


@dataclass(frozen=True)
class MicrobatchCoverageProjection:
    """Physical and fingerprint coverage derived from append-only facts."""

    intervals: tuple[ProjectedMicrobatchInterval, ...] = ()
    contiguous_frontier: str | None = None
    known_missing: tuple[MicrobatchInterval, ...] = ()
    unaccounted: tuple[MicrobatchInterval, ...] = ()
    unknown_fingerprints: tuple[MicrobatchInterval, ...] = ()


@dataclass(frozen=True)
class ReplayRequirementProjection:
    """Derived state of one replay requirement for the expected version."""

    requirement: MicrobatchEvent
    state: ReplayRequirementState
    missing: tuple[MicrobatchInterval, ...] = ()
    unknown_fingerprints: tuple[MicrobatchInterval, ...] = ()
