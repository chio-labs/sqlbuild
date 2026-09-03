"""Construct an exact physical producer completion fact."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.microbatches._helpers.causal_event_identity import producer_completion_event_id
from sqlbuild.microbatches.models import MicrobatchInterval, MicrobatchScope, ProducerCompletion
from sqlbuild.microbatches.types import (
    CausalCompletionKind,
    MicrobatchFingerprintStatus,
    MicrobatchRunType,
)


def physical_producer_completion(
    *,
    scope: MicrobatchScope,
    model_version_hash: str | None,
    interval: MicrobatchInterval,
    run_id: str,
    run_type: MicrobatchRunType,
    created_at: datetime,
) -> ProducerCompletion:
    """Build the known causal fact paired with one applied physical batch."""

    event_id: str = producer_completion_event_id(
        producer_scope=scope,
        producer_model_version_hash=model_version_hash,
        interval_start=interval.start,
        interval_end=interval.end,
        producer_run_id=run_id,
        completion_kind=CausalCompletionKind.PHYSICAL,
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
    )
    return ProducerCompletion(
        event_id=event_id,
        producer_scope=scope,
        producer_model_version_hash=model_version_hash,
        interval=interval,
        producer_run_id=run_id,
        run_type=run_type,
        completion_kind=CausalCompletionKind.PHYSICAL,
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        created_at=created_at,
    )
