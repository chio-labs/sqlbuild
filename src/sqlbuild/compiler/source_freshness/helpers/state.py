"""Shared source freshness state normalization and hashing helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessObservationError
from sqlbuild.compiler.source_freshness.types import SourceFreshnessComparableRecord
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


def source_freshness_records_equivalent(
    *,
    previous_record: SourceFreshnessComparableRecord,
    current_record: SourceFreshnessComparableRecord,
    lag_tolerance: str | None = None,
) -> bool:
    """Return whether two source freshness records are equivalent for skip decisions."""

    if previous_record.data_version_hash == current_record.data_version_hash:
        return True
    if lag_tolerance is None:
        return False
    if previous_record.value_kind != SourceFreshnessValueKind.TIMESTAMP.value:
        return False
    if current_record.value_kind != SourceFreshnessValueKind.TIMESTAMP.value:
        return False
    if previous_record.data_version is None or current_record.data_version is None:
        return False
    previous_timestamp: datetime = _parse_timestamp_data_version(previous_record.data_version)
    current_timestamp: datetime = _parse_timestamp_data_version(current_record.data_version)
    if current_timestamp < previous_timestamp:
        return False
    return current_timestamp - previous_timestamp <= _parse_lag_tolerance(lag_tolerance)


def _parse_timestamp_data_version(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise SourceFreshnessObservationError(
            f"Timestamp source freshness state value is not valid ISO datetime: {value}"
        ) from exc


def _parse_lag_tolerance(value: str) -> timedelta:
    quoted_value_character_count: int = 2
    if len(value) < quoted_value_character_count:
        raise SourceFreshnessObservationError(
            "source freshness lag_tolerance must be a positive duration like 15m, 2h, or 1d"
        )
    unit: str = value[-1]
    amount_text: str = value[:-1]
    if unit not in {"m", "h", "d"} or not amount_text.isdigit():
        raise SourceFreshnessObservationError(
            "source freshness lag_tolerance must be a positive duration like 15m, 2h, or 1d"
        )
    amount: int = int(amount_text)
    if amount <= 0:
        raise SourceFreshnessObservationError(
            "source freshness lag_tolerance must be a positive duration like 15m, 2h, or 1d"
        )
    match unit:
        case "m":
            return timedelta(minutes=amount)
        case "h":
            return timedelta(hours=amount)
        case "d":
            return timedelta(days=amount)
    raise SourceFreshnessObservationError(
        "source freshness lag_tolerance must be a positive duration like 15m, 2h, or 1d"
    )
