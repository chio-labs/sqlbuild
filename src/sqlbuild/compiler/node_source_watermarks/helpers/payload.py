"""Payload encoding helpers for node source watermark state."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import cast

from sqlbuild.compiler.node_source_watermarks.exceptions import (
    NodeSourceWatermarkInputError,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkPayload,
    SourceWatermarkEntry,
    UnknownSourceWatermarkEntry,
)


def encode_watermark_payload(payload: NodeSourceWatermarkPayload) -> str:
    """Encode a node source watermark payload as base64 JSON."""

    raw_payload: dict[str, object] = {
        "version": payload.version,
        "complete": payload.complete,
        "sources": [_source_entry_to_json(entry) for entry in payload.sources],
        "unknown_sources": [
            _unknown_source_entry_to_json(entry) for entry in payload.unknown_sources
        ],
    }
    json_text: str = json.dumps(raw_payload, sort_keys=True, separators=(",", ":"))
    return base64.b64encode(json_text.encode("utf-8")).decode("ascii")


def decode_watermark_payload(value: str, *, qualified_name: str) -> NodeSourceWatermarkPayload:
    """Decode a base64 JSON node source watermark payload."""

    try:
        json_text: str = base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
        raw_payload: object = json.loads(json_text)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: expected "
            "base64-encoded JSON. Delete or rebuild the watermark table to regenerate state."
        ) from error
    if not isinstance(raw_payload, dict):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: expected JSON object"
        )
    return NodeSourceWatermarkPayload(
        version=_required_int(raw_payload, "version", qualified_name=qualified_name),
        complete=_required_bool(raw_payload, "complete", qualified_name=qualified_name),
        sources=tuple(
            _source_entry_from_json(item, qualified_name=qualified_name)
            for item in _optional_list(raw_payload, "sources", qualified_name=qualified_name)
        ),
        unknown_sources=tuple(
            _unknown_source_entry_from_json(item, qualified_name=qualified_name)
            for item in _optional_list(
                raw_payload, "unknown_sources", qualified_name=qualified_name
            )
        ),
    )


def _source_entry_to_json(entry: SourceWatermarkEntry) -> dict[str, object]:
    return {
        "source_name": entry.source_name,
        "target_database": entry.target_database,
        "target_schema": entry.target_schema,
        "target_name": entry.target_name,
        "strategy": entry.strategy,
        "value_kind": entry.value_kind,
        "data_version": entry.data_version,
        "data_version_hash": entry.data_version_hash,
        "observed_at": entry.observed_at.isoformat(),
        "watermark_kind": entry.watermark_kind,
    }


def _unknown_source_entry_to_json(entry: UnknownSourceWatermarkEntry) -> dict[str, object]:
    return {
        "source_name": entry.source_name,
        "target_database": entry.target_database,
        "target_schema": entry.target_schema,
        "target_name": entry.target_name,
        "reason": entry.reason,
    }


def _source_entry_from_json(value: object, *, qualified_name: str) -> SourceWatermarkEntry:
    raw_entry: dict[str, object] = _required_dict(value, qualified_name=qualified_name)
    return SourceWatermarkEntry(
        source_name=_required_str(raw_entry, "source_name", qualified_name=qualified_name),
        target_database=_optional_str(raw_entry, "target_database", qualified_name=qualified_name),
        target_schema=_optional_str(raw_entry, "target_schema", qualified_name=qualified_name),
        target_name=_optional_str(raw_entry, "target_name", qualified_name=qualified_name),
        strategy=_required_str(raw_entry, "strategy", qualified_name=qualified_name),
        value_kind=_required_str(raw_entry, "value_kind", qualified_name=qualified_name),
        data_version=_optional_str(raw_entry, "data_version", qualified_name=qualified_name),
        data_version_hash=_required_str(
            raw_entry, "data_version_hash", qualified_name=qualified_name
        ),
        observed_at=_required_datetime(raw_entry, "observed_at", qualified_name=qualified_name),
        watermark_kind=_required_str(raw_entry, "watermark_kind", qualified_name=qualified_name),
    )


def _unknown_source_entry_from_json(
    value: object, *, qualified_name: str
) -> UnknownSourceWatermarkEntry:
    raw_entry: dict[str, object] = _required_dict(value, qualified_name=qualified_name)
    return UnknownSourceWatermarkEntry(
        source_name=_required_str(raw_entry, "source_name", qualified_name=qualified_name),
        target_database=_optional_str(raw_entry, "target_database", qualified_name=qualified_name),
        target_schema=_optional_str(raw_entry, "target_schema", qualified_name=qualified_name),
        target_name=_optional_str(raw_entry, "target_name", qualified_name=qualified_name),
        reason=_required_str(raw_entry, "reason", qualified_name=qualified_name),
    )


def _required_dict(value: object, *, qualified_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: expected object entry"
        )
    return cast(dict[str, object], value)


def _optional_list(
    raw_payload: dict[str, object], key: str, *, qualified_name: str
) -> list[object]:
    value: object = raw_payload.get(key, [])
    if not isinstance(value, list):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: '{key}' must be a list"
        )
    return cast(list[object], value)


def _required_str(raw_entry: dict[str, object], key: str, *, qualified_name: str) -> str:
    value: object = raw_entry.get(key)
    if not isinstance(value, str):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: '{key}' must be a string"
        )
    return value


def _optional_str(raw_entry: dict[str, object], key: str, *, qualified_name: str) -> str | None:
    value: object = raw_entry.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: '{key}' must be a string"
        )
    return value


def _required_int(raw_entry: dict[str, object], key: str, *, qualified_name: str) -> int:
    value: object = raw_entry.get(key)
    if not isinstance(value, int):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: '{key}' must be an int"
        )
    return value


def _required_bool(raw_entry: dict[str, object], key: str, *, qualified_name: str) -> bool:
    value: object = raw_entry.get(key)
    if not isinstance(value, bool):
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: '{key}' must be a bool"
        )
    return value


def _required_datetime(raw_entry: dict[str, object], key: str, *, qualified_name: str) -> datetime:
    value: str = _required_str(raw_entry, key, qualified_name=qualified_name)
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise NodeSourceWatermarkInputError(
            f"Invalid node source watermark payload in {qualified_name}: "
            f"'{key}' must be ISO datetime"
        ) from error
