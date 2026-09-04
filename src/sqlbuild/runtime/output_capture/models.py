"""Immutable output capture records and accounting."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlbuild.runtime.output_capture._helpers.json import freeze_command_output_json
from sqlbuild.runtime.output_capture.constants import (
    COMMAND_OUTPUT_LOSS_RECORD_TYPE,
    COMMAND_OUTPUT_RECORD_TYPE,
    CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION,
    SQLBUILD_COMMAND_OUTPUT_PRODUCER_VERSION,
)
from sqlbuild.runtime.output_capture.exceptions import CommandOutputValidationError
from sqlbuild.runtime.output_capture.types import CommandOutputStream, OutputRecordPriority


@dataclass(frozen=True)
class CommandOutputRecord:
    """One ANSI-free line chunk ready for destination serialization."""

    invocation_id: str
    sequence: int
    occurred_at: datetime
    stream: CommandOutputStream
    message: str
    external_context: Mapping[str, object]
    run_id: str | None = None
    chunk_index: int = 0
    chunk_count: int = 1
    priority: OutputRecordPriority = OutputRecordPriority.BULK
    record_type: str = COMMAND_OUTPUT_RECORD_TYPE
    dropped_records: int = 0
    schema_version: int = CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION
    producer: str = "sqlbuild"
    producer_version: str = field(default=SQLBUILD_COMMAND_OUTPUT_PRODUCER_VERSION)

    def __post_init__(self) -> None:
        """Validate and freeze the known command-output wire contract."""

        for field_name in ("invocation_id", "producer", "producer_version"):
            value: object = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise CommandOutputValidationError(f"{field_name} must be a non-empty string")
        if self.run_id is not None and (not isinstance(self.run_id, str) or not self.run_id):
            raise CommandOutputValidationError("run_id must be null or a non-empty string")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise CommandOutputValidationError("sequence must be a non-negative integer")
        if (
            not isinstance(self.occurred_at, datetime)
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() != UTC.utcoffset(self.occurred_at)
        ):
            raise CommandOutputValidationError("occurred_at must be a timezone-aware UTC datetime")
        if not isinstance(self.stream, CommandOutputStream):
            raise CommandOutputValidationError("stream must be stdout or stderr")
        if not isinstance(self.message, str):
            raise CommandOutputValidationError("message must be a string")
        for field_name, minimum in (
            ("chunk_index", 0),
            ("chunk_count", 1),
            ("dropped_records", 0),
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise CommandOutputValidationError(
                    f"{field_name} must be an integer of at least {minimum}"
                )
        if self.chunk_index >= self.chunk_count:
            raise CommandOutputValidationError("chunk_index must be less than chunk_count")
        if not isinstance(self.priority, OutputRecordPriority):
            raise CommandOutputValidationError("priority must be bulk or terminal")
        if not isinstance(self.record_type, str) or self.record_type not in {
            COMMAND_OUTPUT_RECORD_TYPE,
            COMMAND_OUTPUT_LOSS_RECORD_TYPE,
        }:
            raise CommandOutputValidationError("record_type is unknown")
        if self.record_type == COMMAND_OUTPUT_RECORD_TYPE and self.dropped_records != 0:
            raise CommandOutputValidationError(
                "command_output records must have zero dropped_records"
            )
        if self.record_type == COMMAND_OUTPUT_LOSS_RECORD_TYPE and self.dropped_records < 1:
            raise CommandOutputValidationError(
                "command_output_loss records must report dropped_records"
            )
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION
        ):
            raise CommandOutputValidationError(
                f"schema_version must be {CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION}"
            )
        frozen_context: object = freeze_command_output_json(
            value=self.external_context,
            path="external_context",
        )
        if not isinstance(frozen_context, Mapping):
            raise CommandOutputValidationError("external_context must be a JSON object")
        object.__setattr__(self, "external_context", frozen_context)

    @property
    def record_id(self) -> str:
        """Return a deterministic destination key for this invocation sequence."""

        return f"{self.invocation_id}:command-output:{self.sequence}"


@dataclass(frozen=True)
class CommandOutputCaptureSummary:
    """Best-effort bounded-delivery accounting."""

    accepted: int
    delivered: int
    failed: int
    dropped: int
    queue_depth: int
    queue_capacity: int
    flush_complete: bool


@dataclass(frozen=True)
class OutputCaptureContext:
    """Opaque integration-owned context for one command."""

    external_context: Mapping[str, object]


@dataclass(frozen=True)
class CommandOutputSinkDefinition:
    """Immutable metadata attached to a command-output sink function."""

    name: str
    streams: frozenset[CommandOutputStream]


@dataclass(frozen=True)
class BoundCommandOutputSink:
    """One command-output sink bound to command-scoped provider instances."""

    name: str
    function: Callable[..., object]
    provider_arguments: Mapping[str, object]
    streams: frozenset[CommandOutputStream]
