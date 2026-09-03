"""Public runtime observability serialization and semantic operations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from sqlbuild.runtime.observability._helpers.validation import validate_schema_version
from sqlbuild.runtime.observability.constants import (
    CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION,
    DIAGNOSTIC_ENVELOPE_FIELDS,
    LIFECYCLE_ENVELOPE_FIELDS,
    LIFECYCLE_EVENT_CATALOGS,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import (
    DiagnosticLog,
    LifecycleEvent,
    LifecycleEventDefinition,
    OpaqueLifecycleEvent,
)


def _json_data(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    return value


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _loads_object(*, raw_json: str, envelope_name: str) -> dict[str, Any]:
    try:
        value: Any = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise ObservabilityValidationError(
            f"{envelope_name} is not valid JSON: {error.msg}"
        ) from error
    if not isinstance(value, dict):
        raise ObservabilityValidationError(f"{envelope_name} must be a JSON object")
    return value


def _dumps(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    )


def _reject_unknown_fields(
    *, data: Mapping[str, object], allowed: frozenset[str], envelope_name: str
) -> None:
    unknown: list[str] = sorted(set(data) - allowed)
    if unknown:
        raise ObservabilityValidationError(
            f"known {envelope_name} contains unknown top-level field(s): {', '.join(unknown)}"
        )


def lifecycle_event_to_json(event: LifecycleEvent | OpaqueLifecycleEvent) -> str:
    """Serialize a known or opaque lifecycle event deterministically."""

    if isinstance(event, OpaqueLifecycleEvent):
        return _dumps(_json_data(event.raw))
    return _dumps(
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "schema_version": event.schema_version,
            "producer": event.producer,
            "producer_version": event.producer_version,
            "occurred_at": _timestamp(event.occurred_at),
            "invocation_id": event.invocation_id,
            "run_id": event.run_id,
            "resource_id": event.resource_id,
            "resource_attempt_id": event.resource_attempt_id,
            "operation_id": event.operation_id,
            "statement_id": event.statement_id,
            "payload": _json_data(event.payload),
        }
    )


def lifecycle_event_from_json(raw_json: str) -> LifecycleEvent | OpaqueLifecycleEvent:
    """Decode known v1 events strictly and retain unknown envelopes opaquely."""

    data: dict[str, Any] = _loads_object(raw_json=raw_json, envelope_name="lifecycle event")
    event_type: object = data.get("event_type")
    schema_version_raw: Any = data.get("schema_version")
    validate_schema_version(value=schema_version_raw)
    schema_version: int = cast(int, schema_version_raw)
    version_catalog: Mapping[str, LifecycleEventDefinition] | None = LIFECYCLE_EVENT_CATALOGS.get(
        schema_version
    )
    if (
        version_catalog is None
        or not isinstance(event_type, str)
        or event_type not in version_catalog
    ):
        return OpaqueLifecycleEvent(raw=data)
    _reject_unknown_fields(
        data=data,
        allowed=LIFECYCLE_ENVELOPE_FIELDS,
        envelope_name=f"v{schema_version} lifecycle event",
    )
    try:
        occurred_at_raw: object = data["occurred_at"]
        if not isinstance(occurred_at_raw, str):
            raise ObservabilityValidationError("occurred_at must be an ISO-8601 string")
        occurred_at: datetime = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
        return LifecycleEvent(
            event_id=data["event_id"],
            event_type=event_type,
            schema_version=schema_version,
            producer=data["producer"],
            producer_version=data["producer_version"],
            occurred_at=occurred_at,
            invocation_id=data["invocation_id"],
            run_id=data.get("run_id"),
            resource_id=data.get("resource_id"),
            resource_attempt_id=data.get("resource_attempt_id"),
            operation_id=data.get("operation_id"),
            statement_id=data.get("statement_id"),
            payload=data.get("payload", {}),
        )
    except KeyError as error:
        raise ObservabilityValidationError(
            f"known event {event_type!r} is missing required envelope field {error.args[0]!r}"
        ) from error
    except (TypeError, ValueError) as error:
        if isinstance(error, ObservabilityValidationError):
            raise
        raise ObservabilityValidationError(
            f"known event {event_type!r} has invalid occurred_at: {error}"
        ) from error


def diagnostic_log_to_json(log: DiagnosticLog) -> str:
    """Serialize a structured diagnostic log deterministically."""

    return _dumps(
        {
            "schema_version": log.schema_version,
            "producer": log.producer,
            "producer_version": log.producer_version,
            "occurred_at": _timestamp(log.occurred_at),
            "severity": log.severity,
            "logger": log.logger,
            "source": log.source,
            "message": log.message,
            "fields": _json_data(log.fields),
            "log_stream_id": log.log_stream_id,
            "invocation_id": log.invocation_id,
            "run_id": log.run_id,
            "resource_id": log.resource_id,
            "resource_attempt_id": log.resource_attempt_id,
            "operation_id": log.operation_id,
            "statement_id": log.statement_id,
        }
    )


def diagnostic_log_from_json(raw_json: str) -> DiagnosticLog:
    """Decode and validate a v1 structured diagnostic log."""

    data: dict[str, Any] = _loads_object(raw_json=raw_json, envelope_name="diagnostic log")
    schema_version_raw: Any = data.get("schema_version")
    validate_schema_version(value=schema_version_raw)
    schema_version: int = cast(int, schema_version_raw)
    if schema_version == CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION:
        _reject_unknown_fields(
            data=data, allowed=DIAGNOSTIC_ENVELOPE_FIELDS, envelope_name="v1 diagnostic log"
        )
    try:
        occurred_at_raw: object = data["occurred_at"]
        if not isinstance(occurred_at_raw, str):
            raise ObservabilityValidationError("occurred_at must be an ISO-8601 string")
        return DiagnosticLog(
            schema_version=schema_version,
            producer=data["producer"],
            producer_version=data["producer_version"],
            occurred_at=datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00")),
            severity=data["severity"],
            logger=data["logger"],
            source=data["source"],
            message=data["message"],
            fields=data.get("fields", {}),
            log_stream_id=data.get("log_stream_id"),
            invocation_id=data.get("invocation_id"),
            run_id=data.get("run_id"),
            resource_id=data.get("resource_id"),
            resource_attempt_id=data.get("resource_attempt_id"),
            operation_id=data.get("operation_id"),
            statement_id=data.get("statement_id"),
        )
    except KeyError as error:
        raise ObservabilityValidationError(
            f"diagnostic log is missing required field {error.args[0]!r}"
        ) from error
    except (TypeError, ValueError) as error:
        if isinstance(error, ObservabilityValidationError):
            raise
        raise ObservabilityValidationError(
            f"diagnostic log has invalid occurred_at: {error}"
        ) from error


def is_terminal_event(event: LifecycleEvent) -> bool:
    """Return whether the fact closes its correlated lifecycle scope."""

    return LIFECYCLE_EVENT_CATALOGS[event.schema_version][event.event_type].terminal


def validate_idempotent_duplicate(*, original: LifecycleEvent, duplicate: LifecycleEvent) -> None:
    """Assert that a repeated event ID identifies exactly the same immutable fact."""

    if original.event_id != duplicate.event_id:
        raise ObservabilityValidationError("events do not share an event_id")
    if original != duplicate:
        raise ObservabilityValidationError(
            f"event_id {original.event_id!r} identifies conflicting lifecycle facts"
        )
