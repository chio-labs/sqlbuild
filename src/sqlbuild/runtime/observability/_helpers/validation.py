"""Validation support for immutable observability envelopes."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType

from sqlbuild.runtime.observability.constants import (
    DURATION_MS_FIELD,
    EXIT_CODE_FIELD,
    FORBIDDEN_STATEMENT_PAYLOAD_FIELDS,
    HOOK_PHASES,
    HOOK_TYPES,
    LIFECYCLE_EVENT_CATALOGS,
    MAX_METADATA_BYTES,
    METADATA_FIELD,
    NONNEGATIVE_INTEGER_PAYLOAD_FIELDS,
    OPERATION_EVENT_PREFIX,
    OPERATION_KINDS,
    OPERATION_METADATA_FIELDS,
    OPERATION_NAMES,
    RESOURCE_ATTEMPT_SKIPPED_EVENT,
    RESOURCE_SKIP_CODES,
    RESOURCE_SKIP_MODES,
    RETRY_SCHEDULED_EVENT,
    STATEMENT_EVENT_PREFIX,
    STRING_PAYLOAD_FIELDS,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import LifecycleEvent, LifecycleEventDefinition
from sqlbuild.runtime.observability.types import JSONValue

_HOOK_NAME_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def validate_schema_version(*, value: object) -> None:
    """Validate the shared positive integer schema-version contract."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ObservabilityValidationError(
            "schema_version must be a positive integer excluding bool"
        )


def freeze_json(*, value: object, path: str) -> JSONValue:
    """Validate and recursively freeze a JSON-compatible value."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ObservabilityValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ObservabilityValidationError(f"{path} keys must be strings")
            frozen[key] = freeze_json(value=item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            freeze_json(value=item, path=f"{path}[{index}]") for index, item in enumerate(value)
        )
    raise ObservabilityValidationError(
        f"{path} contains non-JSON value of type {type(value).__name__}"
    )


def validate_required_text(*, value: object, field_name: str) -> None:
    """Validate one required non-empty string field."""

    if not isinstance(value, str) or not value:
        raise ObservabilityValidationError(f"{field_name} must be a non-empty string")


def validate_optional_text(*, value: object, field_name: str) -> None:
    """Validate one optional non-empty string field."""

    if value is not None:
        validate_required_text(value=value, field_name=field_name)


def validate_timestamp(*, value: datetime) -> None:
    """Validate a timezone-aware UTC timestamp."""

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ObservabilityValidationError("occurred_at must be a timezone-aware UTC datetime")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ObservabilityValidationError("occurred_at must use UTC")


def _forbidden_statement_fields(*, value: object) -> set[str]:
    if isinstance(value, Mapping):
        found: set[str] = {
            key
            for key in value
            if isinstance(key, str) and key in FORBIDDEN_STATEMENT_PAYLOAD_FIELDS
        }
        for item in value.values():
            found.update(_forbidden_statement_fields(value=item))
        return found
    if isinstance(value, (list, tuple)):
        found = set()
        for item in value:
            found.update(_forbidden_statement_fields(value=item))
        return found
    return set()


def _plain_json(*, value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(value=item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(value=item) for item in value]
    return value


def _validate_payload_field(*, field_name: str, value: object) -> None:
    if field_name in STRING_PAYLOAD_FIELDS:
        if not isinstance(value, str) or not value:
            raise ObservabilityValidationError(
                f"payload field {field_name!r} must be a non-empty string"
            )
        return
    if field_name in NONNEGATIVE_INTEGER_PAYLOAD_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ObservabilityValidationError(
                f"payload field {field_name!r} must be a nonnegative integer excluding bool"
            )
        return
    if field_name == DURATION_MS_FIELD:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ObservabilityValidationError(
                "payload field 'duration_ms' must be a nonnegative finite number excluding bool"
            )
        return
    if field_name == EXIT_CODE_FIELD:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ObservabilityValidationError(
                "payload field 'exit_code' must be an integer excluding bool"
            )
        return
    if field_name == METADATA_FIELD:
        if not isinstance(value, Mapping):
            raise ObservabilityValidationError("payload field 'metadata' must be a JSON object")
        encoded: bytes = json.dumps(
            _plain_json(value=value),
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > MAX_METADATA_BYTES:
            raise ObservabilityValidationError(
                f"payload field 'metadata' must encode to at most {MAX_METADATA_BYTES} bytes"
            )


def _validate_operation_payload(*, payload: Mapping[str, JSONValue]) -> None:
    operation_kind: JSONValue | None = payload.get("operation_kind")
    if operation_kind is not None and (
        not isinstance(operation_kind, str) or operation_kind not in OPERATION_KINDS
    ):
        raise ObservabilityValidationError("operation_kind must be a catalogued value")
    operation_name: JSONValue | None = payload.get("operation_name")
    if operation_name is not None and (
        not isinstance(operation_name, str) or operation_name not in OPERATION_NAMES
    ):
        raise ObservabilityValidationError("operation_name must be a catalogued value")
    hook_phase: JSONValue | None = payload.get("hook_phase")
    hook_type: JSONValue | None = payload.get("hook_type")
    hook_index: JSONValue | None = payload.get("hook_index")
    hook_name: JSONValue | None = payload.get("hook_name")
    hook_fields_present: bool = any(
        value is not None for value in (hook_phase, hook_type, hook_index, hook_name)
    )
    if hook_fields_present:
        if hook_phase not in HOOK_PHASES:
            raise ObservabilityValidationError("hook_phase must be a catalogued value")
        if hook_type not in HOOK_TYPES:
            raise ObservabilityValidationError("hook_type must be a catalogued value")
        if isinstance(hook_index, bool) or not isinstance(hook_index, int) or hook_index < 0:
            raise ObservabilityValidationError("hook_index must be a nonnegative integer")
        if hook_name is not None and (
            not isinstance(hook_name, str) or _HOOK_NAME_PATTERN.fullmatch(hook_name) is None
        ):
            raise ObservabilityValidationError("hook_name must be a non-empty safe token")
    metadata: JSONValue | None = payload.get(METADATA_FIELD)
    if metadata is None:
        return
    if not isinstance(metadata, Mapping):
        raise ObservabilityValidationError("operation metadata must be a JSON object")
    if set(metadata) - OPERATION_METADATA_FIELDS:
        raise ObservabilityValidationError("operation metadata contains a non-allowlisted field")
    for value in metadata.values():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ObservabilityValidationError(
                "operation metadata values must be nonnegative integers excluding bool"
            )


def validate_known_lifecycle_event(*, event: LifecycleEvent) -> None:
    """Validate correlations and safe payload fields for a catalogued event."""

    version_catalog: Mapping[str, LifecycleEventDefinition] | None = LIFECYCLE_EVENT_CATALOGS.get(
        event.schema_version
    )
    definition: LifecycleEventDefinition | None = (
        version_catalog.get(event.event_type) if version_catalog is not None else None
    )
    if definition is None:
        raise ObservabilityValidationError(
            f"unknown lifecycle event_type {event.event_type!r}; decode it as an opaque envelope"
        )
    missing: list[str] = sorted(
        field_name
        for field_name in definition.required_correlations
        if getattr(event, field_name) is None
    )
    if missing:
        raise ObservabilityValidationError(
            f"known event {event.event_type!r} requires correlation field(s): {', '.join(missing)}"
        )
    missing_payload: list[str] = sorted(definition.required_payload_fields - set(event.payload))
    if missing_payload:
        raise ObservabilityValidationError(
            f"known event {event.event_type!r} requires payload field(s): "
            f"{', '.join(missing_payload)}"
        )
    unexpected: list[str] = sorted(set(event.payload) - definition.allowed_payload_fields)
    if unexpected:
        allowed: str = ", ".join(sorted(definition.allowed_payload_fields)) or "none"
        raise ObservabilityValidationError(
            f"payload field(s) not allowed for known event {event.event_type!r}: "
            f"{', '.join(unexpected)}; allowed fields: {allowed}"
        )
    if event.event_type.startswith(STATEMENT_EVENT_PREFIX):
        forbidden: list[str] = sorted(_forbidden_statement_fields(value=event.payload))
        if forbidden:
            raise ObservabilityValidationError(
                f"statement lifecycle payload must not contain SQL or parameter values; "
                f"forbidden field(s): {', '.join(forbidden)}"
            )
    if event.event_type.startswith(OPERATION_EVENT_PREFIX):
        _validate_operation_payload(payload=event.payload)
    if event.event_type == RESOURCE_ATTEMPT_SKIPPED_EVENT:
        if event.payload.get("skip_code") not in RESOURCE_SKIP_CODES:
            raise ObservabilityValidationError("skip_code must be a catalogued value")
        skip_mode: JSONValue | None = event.payload.get("skip_mode")
        if skip_mode is not None and skip_mode not in RESOURCE_SKIP_MODES:
            raise ObservabilityValidationError("skip_mode must be a catalogued value")
    if event.event_type == RETRY_SCHEDULED_EVENT:
        failed_attempt: JSONValue | None = event.payload.get("failed_attempt_number")
        next_attempt: JSONValue | None = event.payload.get("next_attempt_number")
        if (
            not isinstance(failed_attempt, int)
            or isinstance(failed_attempt, bool)
            or failed_attempt <= 0
        ):
            raise ObservabilityValidationError("failed_attempt_number must be a positive integer")
        if (
            not isinstance(next_attempt, int)
            or isinstance(next_attempt, bool)
            or next_attempt != failed_attempt + 1
        ):
            raise ObservabilityValidationError(
                "next_attempt_number must equal failed_attempt_number + 1"
            )
    for field_name, value in event.payload.items():
        _validate_payload_field(field_name=field_name, value=value)
