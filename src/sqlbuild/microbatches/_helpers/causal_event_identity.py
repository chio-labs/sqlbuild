"""Content-addressed identities for causal microbatch facts."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.microbatches.models import ConsumedProducerInterval, MicrobatchScope
from sqlbuild.microbatches.types import CausalCompletionKind, MicrobatchFingerprintStatus


def producer_completion_event_id(
    *,
    producer_scope: MicrobatchScope,
    producer_model_version_hash: str | None,
    interval_start: str,
    interval_end: str,
    producer_run_id: str,
    completion_kind: CausalCompletionKind,
    fingerprint_status: MicrobatchFingerprintStatus,
) -> str:
    """Identify one producer application independently of publication retries."""

    return _causal_id(
        "producer_completion",
        _scope_identity(producer_scope),
        producer_model_version_hash,
        interval_start,
        interval_end,
        producer_run_id,
        completion_kind.value,
        fingerprint_status.value,
    )


def consumer_frontier_event_id(
    *,
    consumer_scope: MicrobatchScope,
    consumer_model_version_hash: str | None,
    producer_scope: MicrobatchScope,
    producer_model_version_hash: str | None,
    captured_producer_event_ids: frozenset[str],
    consumer_run_id: str,
    consumed_intervals: tuple[ConsumedProducerInterval, ...] = (),
) -> str:
    """Identify one exact consumer acknowledgement snapshot."""

    return _causal_id(
        "consumer_frontier",
        _scope_identity(consumer_scope),
        consumer_model_version_hash,
        _scope_identity(producer_scope),
        producer_model_version_hash,
        tuple(sorted(captured_producer_event_ids)),
        tuple(
            sorted(
                (item.producer_event_id, item.interval.start, item.interval.end)
                for item in consumed_intervals
            )
        ),
        consumer_run_id,
    )


def _scope_identity(scope: MicrobatchScope) -> tuple[object, ...]:
    return (
        scope.scope_kind,
        scope.scope_key,
        scope.model_name,
        scope.target_database,
        scope.target_schema,
        scope.target_name,
        scope.physical_generation_id,
        scope.virtual_environment_name,
        scope.virtual_model_version_hash,
    )


def _causal_id(*identity: object) -> str:
    encoded: str = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
