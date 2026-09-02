"""Strict bounded validation and encoding for integration-result values."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence

from sqlbuild.cli.output.constants import (
    INTEGRATION_MAXIMUM_START_ACTIONS,
    INTEGRATION_MAXIMUM_START_INPUT_KEYS,
    INTEGRATION_MAXIMUM_START_KEYS,
    INTEGRATION_MAXIMUM_START_REQUIRED_KEYS,
    MAX_INTEGRATION_COLLECTION_ITEMS,
    MAX_INTEGRATION_IDENTIFIER_CHARS,
    MAX_INTEGRATION_METADATA_BYTES,
    MAX_INTEGRATION_NESTING_DEPTH,
    MAX_INTEGRATION_RECORD_BYTES,
    MAX_INTEGRATION_STRING_CHARS,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.types import JSONValue


def encode_integration_json(*, value: object, record: bool = False) -> str:
    """Encode a validated JSON value using deterministic strict JSON settings."""

    validate_json_value(value=value, depth=0)
    try:
        encoded: str = json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ObservabilityValidationError("integration value is not strict JSON") from error
    limit: int = MAX_INTEGRATION_RECORD_BYTES if record else MAX_INTEGRATION_METADATA_BYTES
    if len(encoded.encode("utf-8")) > limit:
        raise ObservabilityValidationError("integration JSON exceeds size limit")
    return encoded


def validate_json_value(*, value: object, depth: int) -> None:
    """Reject unsafe, non-JSON, deeply nested, or oversized integration values."""

    if depth > MAX_INTEGRATION_NESTING_DEPTH:
        raise ObservabilityValidationError("integration JSON exceeds nesting limit")
    if value is None or type(value) is bool or type(value) is int:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ObservabilityValidationError("integration JSON numbers must be finite")
        return
    if type(value) is str:
        if len(value) > MAX_INTEGRATION_STRING_CHARS:
            raise ObservabilityValidationError("integration JSON string exceeds size limit")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_INTEGRATION_COLLECTION_ITEMS:
            raise ObservabilityValidationError("integration JSON object exceeds item limit")
        for key, item in value.items():
            if type(key) is not str:
                raise ObservabilityValidationError("integration JSON object keys must be strings")
            if not key or len(key) > MAX_INTEGRATION_IDENTIFIER_CHARS:
                raise ObservabilityValidationError("integration JSON object key is invalid")
            validate_json_value(value=item, depth=depth + 1)
        return
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        if len(value) > MAX_INTEGRATION_COLLECTION_ITEMS:
            raise ObservabilityValidationError("integration JSON array exceeds item limit")
        for item in value:
            validate_json_value(value=item, depth=depth + 1)
        return
    raise ObservabilityValidationError("integration value is not JSON")


def validate_identifier(*, value: object, field_name: str) -> None:
    """Validate one required bounded integration identifier."""

    if type(value) is not str or not value or len(value) > MAX_INTEGRATION_IDENTIFIER_CHARS:
        raise ObservabilityValidationError(f"integration {field_name} is invalid")


def validate_optional_identifier(*, value: object, field_name: str) -> None:
    """Validate one optional bounded integration identifier."""

    if value is not None:
        validate_identifier(value=value, field_name=field_name)


def validate_maximum_start_safety(value: Mapping[str, JSONValue]) -> None:
    """Validate the exact bounded structure emitted by the shared final JSON serializer."""

    validate_allowlisted_mapping(
        value=value,
        field_name="maximum_start_safety",
        allowed_keys=INTEGRATION_MAXIMUM_START_KEYS,
    )
    if not value:
        return
    if set(value) != INTEGRATION_MAXIMUM_START_REQUIRED_KEYS:
        raise ObservabilityValidationError(
            "integration maximum_start_safety must use the canonical structure"
        )
    if value.get("action") not in INTEGRATION_MAXIMUM_START_ACTIONS:
        raise ObservabilityValidationError("integration maximum_start_safety action is unsupported")
    optional_text_fields: frozenset[str] = frozenset({"highest_eligible_target_max"})
    for field_name in INTEGRATION_MAXIMUM_START_REQUIRED_KEYS - {"action", "input"}:
        field_value: object = value.get(field_name)
        if type(field_value) is not str and not (
            field_name in optional_text_fields and field_value is None
        ):
            raise ObservabilityValidationError(
                f"integration maximum_start_safety {field_name} has an invalid type"
            )
    input_value: object = value.get("input")
    if (
        not isinstance(input_value, Mapping)
        or set(input_value) != INTEGRATION_MAXIMUM_START_INPUT_KEYS
    ):
        raise ObservabilityValidationError(
            "integration maximum_start_safety input must use the canonical structure"
        )
    if any(type(item) is not str or not item for item in input_value.values()):
        raise ObservabilityValidationError(
            "integration maximum_start_safety input values must be non-empty strings"
        )


def validate_allowlisted_mapping(
    *, value: object, field_name: str, allowed_keys: frozenset[str]
) -> None:
    """Validate one framework-generated bounded scalar mapping."""

    if not isinstance(value, Mapping):
        raise ObservabilityValidationError(f"integration {field_name} must be an object")
    if any(type(key) is not str for key in value):
        raise ObservabilityValidationError(f"integration {field_name} keys must be strings")
    if not set(value).issubset(allowed_keys):
        raise ObservabilityValidationError(f"integration {field_name} contains unknown fields")
    _ = encode_integration_json(value=value)
    _validate_nested_mapping_keys(
        value=value,
        field_name=field_name,
        allowed_keys=allowed_keys,
    )


def _validate_nested_mapping_keys(
    *, value: object, field_name: str, allowed_keys: frozenset[str]
) -> None:
    if isinstance(value, Mapping):
        if not set(value).issubset(allowed_keys):
            raise ObservabilityValidationError(f"integration {field_name} contains unknown fields")
        for item in value.values():
            _validate_nested_mapping_keys(
                value=item,
                field_name=field_name,
                allowed_keys=allowed_keys,
            )
        return
    if isinstance(value, list | tuple):
        for item in value:
            _validate_nested_mapping_keys(
                value=item,
                field_name=field_name,
                allowed_keys=allowed_keys,
            )
