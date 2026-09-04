"""Serialize one command-output record into its canonical wire format."""

from __future__ import annotations

import json
from collections.abc import Mapping

from sqlbuild.runtime.output_capture.models import CommandOutputRecord


def _json_data(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    return value


def command_output_to_json(record: CommandOutputRecord) -> str:
    """Serialize one command-output record deterministically."""

    return json.dumps(
        {
            "record_id": record.record_id,
            "record_type": record.record_type,
            "schema_version": record.schema_version,
            "producer": record.producer,
            "producer_version": record.producer_version,
            "occurred_at": record.occurred_at.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            "invocation_id": record.invocation_id,
            "run_id": record.run_id,
            "sequence": record.sequence,
            "stream": record.stream.value,
            "message": record.message,
            "chunk_index": record.chunk_index,
            "chunk_count": record.chunk_count,
            "priority": record.priority.value,
            "dropped_records": record.dropped_records,
            "external_context": _json_data(record.external_context),
        },
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
