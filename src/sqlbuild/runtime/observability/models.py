"""Immutable lifecycle fact and diagnostic log envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Self

from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.types import JSONValue


@dataclass(frozen=True)
class OperationAttributes:
    """Optional catalogued operation dimensions."""

    phase: str | None = None
    strategy: str | None = None
    adapter: str | None = None
    target_kind: str | None = None


@dataclass(frozen=True)
class ExecutionIdentity:
    """Immutable correlation identity for one point in an execution hierarchy."""

    invocation_id: str
    run_id: str | None = None
    resource_id: str | None = None
    resource_attempt_id: str | None = None
    operation_id: str | None = None
    statement_id: str | None = None
    log_stream_id: str | None = None

    def __post_init__(self) -> None:
        from sqlbuild.runtime.observability._helpers.validation import (
            validate_optional_text,
            validate_required_text,
        )

        validate_required_text(value=self.invocation_id, field_name="invocation_id")
        for field_name in (
            "run_id",
            "resource_id",
            "resource_attempt_id",
            "operation_id",
            "statement_id",
            "log_stream_id",
        ):
            validate_optional_text(value=getattr(self, field_name), field_name=field_name)


@dataclass(frozen=True)
class LifecycleEventDefinition:
    """Validation contract for one known lifecycle event type."""

    required_correlations: frozenset[str]
    required_payload_fields: frozenset[str]
    allowed_payload_fields: frozenset[str]
    terminal: bool

    @classmethod
    def create(
        cls,
        *,
        required_correlations: frozenset[str] = frozenset(),
        required_payload: frozenset[str] = frozenset(),
        allowed: frozenset[str] = frozenset(),
        terminal: bool = False,
    ) -> Self:
        """Create one immutable catalog definition."""

        return cls(required_correlations, required_payload, allowed, terminal)


@dataclass(frozen=True)
class LifecycleEvent:
    """A canonical immutable lifecycle fact using the current known schema."""

    event_id: str
    event_type: str
    schema_version: int
    producer: str
    producer_version: str
    occurred_at: datetime
    invocation_id: str
    run_id: str | None = None
    resource_id: str | None = None
    resource_attempt_id: str | None = None
    operation_id: str | None = None
    statement_id: str | None = None
    payload: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from sqlbuild.runtime.observability._helpers.validation import (
            freeze_json,
            validate_known_lifecycle_event,
            validate_optional_text,
            validate_required_text,
            validate_schema_version,
            validate_timestamp,
        )

        for field_name in (
            "event_id",
            "event_type",
            "producer",
            "producer_version",
            "invocation_id",
        ):
            validate_required_text(value=getattr(self, field_name), field_name=field_name)
        validate_schema_version(value=self.schema_version)
        if self.schema_version != 1:
            raise ObservabilityValidationError(
                "LifecycleEvent only represents known schema version 1; "
                "decode newer versions as OpaqueLifecycleEvent"
            )
        validate_timestamp(value=self.occurred_at)
        for field_name in (
            "run_id",
            "resource_id",
            "resource_attempt_id",
            "operation_id",
            "statement_id",
        ):
            validate_optional_text(value=getattr(self, field_name), field_name=field_name)
        frozen_payload: JSONValue = freeze_json(value=self.payload, path="payload")
        if not isinstance(frozen_payload, Mapping):
            raise ObservabilityValidationError("payload must be a JSON object")
        object.__setattr__(self, "payload", frozen_payload)
        validate_known_lifecycle_event(event=self)


@dataclass(frozen=True)
class OpaqueLifecycleEvent:
    """An immutable unknown lifecycle envelope retained without schema coercion."""

    raw: Mapping[str, JSONValue]

    def __post_init__(self) -> None:
        from sqlbuild.runtime.observability._helpers.validation import freeze_json

        frozen_raw: JSONValue = freeze_json(value=self.raw, path="event")
        if not isinstance(frozen_raw, Mapping):
            raise ObservabilityValidationError("event must be a JSON object")
        object.__setattr__(self, "raw", frozen_raw)


@dataclass(frozen=True)
class DiagnosticLog:
    """A structured diagnostic record, intentionally distinct from lifecycle facts."""

    schema_version: int
    producer: str
    producer_version: str
    occurred_at: datetime
    severity: str
    logger: str
    source: str
    message: str
    fields: Mapping[str, JSONValue] = field(default_factory=dict)
    log_stream_id: str | None = None
    invocation_id: str | None = None
    run_id: str | None = None
    resource_id: str | None = None
    resource_attempt_id: str | None = None
    operation_id: str | None = None
    statement_id: str | None = None

    def __post_init__(self) -> None:
        from sqlbuild.runtime.observability._helpers.validation import (
            freeze_json,
            validate_optional_text,
            validate_required_text,
            validate_schema_version,
            validate_timestamp,
        )
        from sqlbuild.runtime.observability.constants import DIAGNOSTIC_SEVERITIES

        validate_schema_version(value=self.schema_version)
        if self.schema_version != 1:
            raise ObservabilityValidationError("diagnostic schema_version must be 1")
        for field_name in (
            "producer",
            "producer_version",
            "severity",
            "logger",
            "source",
            "message",
        ):
            validate_required_text(value=getattr(self, field_name), field_name=field_name)
        if self.severity not in DIAGNOSTIC_SEVERITIES:
            raise ObservabilityValidationError(
                "severity must be one of trace, debug, info, warning, error, critical"
            )
        validate_timestamp(value=self.occurred_at)
        for field_name in (
            "log_stream_id",
            "invocation_id",
            "run_id",
            "resource_id",
            "resource_attempt_id",
            "operation_id",
            "statement_id",
        ):
            validate_optional_text(value=getattr(self, field_name), field_name=field_name)
        frozen_fields: JSONValue = freeze_json(value=self.fields, path="fields")
        if not isinstance(frozen_fields, Mapping):
            raise ObservabilityValidationError("fields must be a JSON object")
        object.__setattr__(self, "fields", frozen_fields)


@dataclass(frozen=True)
class DispatchFailure:
    """Bounded health record for one isolated subscriber failure."""

    channel: Literal["lifecycle", "diagnostic"]
    subscriber: str
    error_type: str
    message: str
