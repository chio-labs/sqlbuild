"""Helpers for storing source freshness observations in virtual state."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.virtual.freshness.models import SourceFreshnessObservation
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def source_freshness_record_from_observation(
    observation: SourceFreshnessObservation, *, virtual_environment_name: str
) -> SourceFreshnessRecord:
    """Build a persisted state record from an observed source freshness value."""

    normalized_data_version: str = normalize_source_freshness_data_version(
        value=observation.data_version,
        value_kind=observation.value_kind,
    )
    return SourceFreshnessRecord(
        virtual_environment_name=virtual_environment_name,
        source_name=observation.source_name,
        strategy=observation.strategy.value,
        value_kind=observation.value_kind.value,
        data_version=normalized_data_version,
        data_version_hash=source_freshness_data_version_hash(
            source_name=observation.source_name,
            strategy=observation.strategy,
            value_kind=observation.value_kind,
            data_version=normalized_data_version,
        ),
        observed_at=observation.observed_at,
    )


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
