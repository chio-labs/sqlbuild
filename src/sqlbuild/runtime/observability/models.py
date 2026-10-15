"""Immutable lifecycle fact and diagnostic log envelopes."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlbuild._native import (
    freeze_lifecycle_json,
    validate_diagnostic_log,
    validate_lifecycle_event,
    validate_lifecycle_invocation_sequence,
    validate_lifecycle_optional_text,
    validate_lifecycle_required_text,
)
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.types import JSONValue


@dataclass(frozen=True)
class OperationAttributes:
    """Optional catalogued operation dimensions."""

    phase: str | None = None
    strategy: str | None = None
    adapter: str | None = None
    target_kind: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class MicrobatchLifecycleContext:
    """Bounded execution context repeated across one microbatch lifecycle."""

    cursor_start: str
    cursor_end_exclusive: str
    planned_cursor_start: str
    planned_cursor_end_exclusive: str
    batch_index: int
    batch_count: int
    configured_batch_size: str
    effective_batch_size: str
    microbatch_strategy: str
    microbatch_run_type: str
    batch_kind: str

    def payload(self) -> dict[str, JSONValue]:
        return {
            "cursor_start": self.cursor_start,
            "cursor_end_exclusive": self.cursor_end_exclusive,
            "planned_cursor_start": self.planned_cursor_start,
            "planned_cursor_end_exclusive": self.planned_cursor_end_exclusive,
            "batch_index": self.batch_index,
            "batch_count": self.batch_count,
            "configured_batch_size": self.configured_batch_size,
            "effective_batch_size": self.effective_batch_size,
            "microbatch_strategy": self.microbatch_strategy,
            "microbatch_run_type": self.microbatch_run_type,
            "batch_kind": self.batch_kind,
        }


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

        validate_lifecycle_required_text(value=self.invocation_id, field_name="invocation_id")
        for field_name in (
            "run_id",
            "resource_id",
            "resource_attempt_id",
            "operation_id",
            "statement_id",
            "log_stream_id",
        ):
            validate_lifecycle_optional_text(value=getattr(self, field_name), field_name=field_name)


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
    invocation_sequence: int | None = None
    run_id: str | None = None
    resource_id: str | None = None
    resource_attempt_id: str | None = None
    operation_id: str | None = None
    statement_id: str | None = None
    external_context: Mapping[str, JSONValue] = field(default_factory=dict)
    payload: Mapping[str, JSONValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_lifecycle_event(event=self)

    def with_invocation_sequence(self, sequence: int) -> LifecycleEvent:
        """Return this validated event with a dispatcher-assigned invocation sequence."""

        validate_lifecycle_invocation_sequence(value=sequence)
        sequenced: LifecycleEvent = copy.copy(self)
        object.__setattr__(sequenced, "invocation_sequence", sequence)
        return sequenced


@dataclass(frozen=True)
class OpaqueLifecycleEvent:
    """An immutable unknown lifecycle envelope retained without schema coercion."""

    raw: Mapping[str, JSONValue]

    def __post_init__(self) -> None:
        frozen_raw: JSONValue = freeze_lifecycle_json(value=self.raw, path="event")
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
        validate_diagnostic_log(record=self)


@dataclass(frozen=True)
class DispatchFailure:
    """Bounded health record for one isolated subscriber failure."""

    channel: Literal["lifecycle", "diagnostic"]
    subscriber: str
    error_type: str
    message: str
