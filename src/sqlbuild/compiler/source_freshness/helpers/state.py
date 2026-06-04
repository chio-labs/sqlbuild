"""Shared source freshness state normalization and hashing helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind


def normalize_source_freshness_data_version(
    *, value: object, value_kind: SourceFreshnessValueKind
) -> str:
    """Normalize a source freshness value for stable state storage."""

    match value_kind:
        case SourceFreshnessValueKind.TIMESTAMP:
            if not isinstance(value, datetime):
                raise SourceFreshnessObservationError(
                    "Timestamp source freshness values must be datetime values"
                )
            normalized: datetime = value
            if normalized.tzinfo is not None:
                normalized = normalized.astimezone(UTC)
            return normalized.isoformat()
        case SourceFreshnessValueKind.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                raise SourceFreshnessObservationError(
                    "Integer source freshness values must be integer values"
                )
            return str(value)
        case SourceFreshnessValueKind.STRING:
            if not isinstance(value, str):
                raise SourceFreshnessObservationError(
                    "String source freshness values must be string values"
                )
            return value
    raise SourceFreshnessObservationError(f"Unsupported source freshness value kind: {value_kind}")


def source_freshness_data_version_hash(
    *,
    source_name: str,
    strategy: SourceFreshnessStrategy | str,
    value_kind: SourceFreshnessValueKind | str,
    data_version: str,
) -> str:
    """Hash the stable source freshness identity used as a graph input."""

    payload: dict[str, str] = {
        "source_name": source_name,
        "strategy": strategy.value if isinstance(strategy, SourceFreshnessStrategy) else strategy,
        "value_kind": value_kind.value
        if isinstance(value_kind, SourceFreshnessValueKind)
        else value_kind,
        "data_version": data_version,
    }
    encoded: bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
