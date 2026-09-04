"""Deserialize and validate one canonical command-output record."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from sqlbuild.runtime.output_capture.constants import (
    COMMAND_OUTPUT_ENVELOPE_FIELDS,
    COMMAND_OUTPUT_LOSS_RECORD_TYPE,
    COMMAND_OUTPUT_RECORD_TYPE,
    CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION,
)
from sqlbuild.runtime.output_capture.exceptions import CommandOutputValidationError
from sqlbuild.runtime.output_capture.models import CommandOutputRecord
from sqlbuild.runtime.output_capture.types import CommandOutputStream, OutputRecordPriority


def command_output_from_json(raw_json: str) -> CommandOutputRecord:
    """Deserialize one known command-output record strictly."""

    try:
        raw: object = json.loads(raw_json)
    except (TypeError, ValueError) as error:
        raise CommandOutputValidationError("command output must be valid JSON") from error
    if not isinstance(raw, dict):
        raise CommandOutputValidationError("command output must be a JSON object")
    data: dict[str, Any] = cast(dict[str, Any], raw)
    unknown: frozenset[str] = frozenset(data) - COMMAND_OUTPUT_ENVELOPE_FIELDS
    missing: frozenset[str] = COMMAND_OUTPUT_ENVELOPE_FIELDS - frozenset(data)
    if unknown or missing:
        raise CommandOutputValidationError("command output fields do not match schema version 1")
    if (
        isinstance(data["schema_version"], bool)
        or not isinstance(data["schema_version"], int)
        or data["schema_version"] != CURRENT_COMMAND_OUTPUT_SCHEMA_VERSION
    ):
        raise CommandOutputValidationError("unsupported command output schema version")
    if not isinstance(data["record_type"], str) or data["record_type"] not in {
        COMMAND_OUTPUT_RECORD_TYPE,
        COMMAND_OUTPUT_LOSS_RECORD_TYPE,
    }:
        raise CommandOutputValidationError("unknown command output record type")
    context: object = data["external_context"]
    if not isinstance(context, dict):
        raise CommandOutputValidationError("command output external_context must be an object")
    try:
        record: CommandOutputRecord = CommandOutputRecord(
            invocation_id=data["invocation_id"],
            run_id=data["run_id"],
            sequence=data["sequence"],
            occurred_at=_occurred_at(data["occurred_at"]),
            stream=CommandOutputStream(data["stream"]),
            message=data["message"],
            external_context=context,
            chunk_index=data["chunk_index"],
            chunk_count=data["chunk_count"],
            priority=OutputRecordPriority(data["priority"]),
            record_type=data["record_type"],
            dropped_records=data["dropped_records"],
            schema_version=data["schema_version"],
            producer=data["producer"],
            producer_version=data["producer_version"],
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, CommandOutputValidationError):
            raise
        raise CommandOutputValidationError(
            "command output contains invalid field values"
        ) from error
    if data["record_id"] != record.record_id:
        raise CommandOutputValidationError("command output record_id does not match its identity")
    return record


def _occurred_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise CommandOutputValidationError("occurred_at must be an ISO-8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CommandOutputValidationError("occurred_at must be an ISO-8601 string") from error
