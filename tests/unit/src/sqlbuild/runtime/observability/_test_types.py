"""Frozen parameter cases for runtime observability tests."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from sqlbuild.runtime.observability.models import OpaqueLifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue


@dataclass(frozen=True)
class EventCase:
    description: str
    event_type: str
    expected_event_type: str
    run_id: str | None = None
    resource_id: str | None = None
    resource_attempt_id: str | None = None
    operation_id: str | None = None
    statement_id: str | None = None


@dataclass(frozen=True)
class StatementPrivacyCase:
    description: str
    field_name: str
    value: JSONValue
    expected_error: str


@dataclass(frozen=True)
class LifecycleErrorCase:
    description: str
    event_type: str
    payload: Mapping[str, JSONValue]
    expected_error: str
    run_id: str | None = None
    resource_id: str | None = None
    statement_id: str | None = None


@dataclass(frozen=True)
class TimestampErrorCase:
    description: str
    occurred_at: datetime
    expected_error: str


@dataclass(frozen=True)
class TerminalSemanticsCase:
    description: str
    event_types: tuple[str, ...]
    expected_terminal: tuple[bool, ...]


@dataclass(frozen=True)
class TerminalEvidenceCase:
    description: str
    expected_terminal_count: int


@dataclass(frozen=True)
class CatalogVersionCase:
    description: str
    schema_version: int
    event_type: str
    expected_terminal: bool
    expected_unsupported_version: int


@dataclass(frozen=True)
class IdempotencyCase:
    description: str
    duplicate_command: str | None
    expected_event_id: str
    expected_error: str


@dataclass(frozen=True)
class ImmutabilityCase:
    description: str
    command: str
    expected_command: str


@dataclass(frozen=True)
class SchemaVersionCase:
    description: str
    schema_version: object
    expected_error: str


@dataclass(frozen=True)
class ExactJsonCase:
    description: str
    payload: Mapping[str, JSONValue]
    expected_json: str


@dataclass(frozen=True)
class OpaqueRoundTripCase:
    description: str
    raw: Mapping[str, JSONValue]
    expected_raw: Mapping[str, JSONValue]


@dataclass(frozen=True)
class JsonErrorCase:
    description: str
    encoded: str
    expected_error: str


@dataclass(frozen=True)
class StatementRoundTripCase:
    description: str
    payload: Mapping[str, JSONValue]
    expected_affected_rows: int


@dataclass(frozen=True)
class MetadataBoundaryCase:
    description: str
    metadata_value: str
    expected_encoded_size: int


@dataclass(frozen=True)
class DiagnosticRoundTripCase:
    description: str
    severity: str
    message: str
    expected_message: str


@dataclass(frozen=True)
class DiagnosticSeparationCase:
    description: str
    expected_type: type[OpaqueLifecycleEvent]


@dataclass(frozen=True)
class EnvelopeFieldErrorCase:
    description: str
    field_name: str
    field_value: JSONValue
    expected_error: str


@dataclass(frozen=True)
class IdentityFieldErrorCase:
    description: str
    field_name: str
    field_value: object
    expected_error: str


@dataclass(frozen=True)
class IdentityBehaviorCase:
    description: str
    expected_invocation_id: str
