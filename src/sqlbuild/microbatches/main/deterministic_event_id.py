"""Build stable identifiers for immutable logical microbatch events."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.microbatches.models import MicrobatchScope
from sqlbuild.microbatches.types import MicrobatchRecordType


def deterministic_microbatch_event_id(
    *,
    scope: MicrobatchScope,
    record_type: MicrobatchRecordType,
    partition_start: str | None,
    partition_end: str | None,
    completion_reason: str,
) -> str:
    """Return the content-addressed ID for one logical event."""

    identity: tuple[object, ...] = (
        scope.scope_kind,
        scope.scope_key,
        scope.model_name,
        scope.target_database,
        scope.target_schema,
        scope.target_name,
        scope.physical_generation_id,
        scope.virtual_environment_name,
        scope.virtual_model_version_hash,
        record_type.value,
        partition_start,
        partition_end,
        completion_reason,
    )
    encoded: str = json.dumps(identity, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
