"""Stable physical encoding for logical microbatch events."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlbuild.microbatches.constants import (
    MICROBATCH_COLUMNS,
    RETIRED_MICROBATCH_RECORD_TYPES,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
from sqlbuild.microbatches.types import (
    MicrobatchCompletionType,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
    UnaccountedPartitionPolicy,
)

_RECORD_TYPE_COLUMN_INDEX: int = MICROBATCH_COLUMNS.index("record_type")


class MicrobatchEventCodec:
    """Encode and decode the shared event schema in stable column order."""

    @staticmethod
    def values(event: MicrobatchEvent) -> tuple[object | None, ...]:
        return (
            event.event_id,
            event.record_type.value,
            event.scope.scope_kind,
            event.scope.scope_key,
            event.scope.model_name,
            event.scope.target_database,
            event.scope.target_schema,
            event.scope.target_name,
            event.scope.physical_generation_id,
            event.scope.virtual_environment_name,
            event.scope.virtual_model_version_hash,
            event.origin_run_id,
            event.origin_run_started_at,
            event.execution_run_id,
            event.execution_run_started_at,
            event.run_type.value,
            None if event.completion_type is None else event.completion_type.value,
            event.run_start,
            event.run_end,
            event.partition_start,
            event.partition_end,
            event.batch_size,
            event.cursor_column,
            event.cursor_type,
            event.cursor_grain,
            event.model_version_hash,
            event.definition_hash,
            event.fingerprint_status.value,
            event.replay_requirement_id,
            event.required_model_version_hash,
            event.previous_model_version_hash,
            event.replay_policy,
            event.rows_affected,
            event.completed_at,
            event.coverage_source,
            event.observed_row_count,
            event.observed_at,
            event.synthetic_reason,
            None if event.unaccounted_policy is None else event.unaccounted_policy.value,
            event.created_at,
        )

    @staticmethod
    def from_row(row: tuple[Any, ...]) -> MicrobatchEvent:
        values: dict[str, Any] = dict(zip(MICROBATCH_COLUMNS, row, strict=True))
        scope: MicrobatchScope = MicrobatchScope(
            scope_kind=str(values["scope_kind"]),
            scope_key=str(values["scope_key"]),
            model_name=str(values["model_name"]),
            target_database=MicrobatchEventCodec._optional_str(values["target_database"]),
            target_schema=MicrobatchEventCodec._optional_str(values["target_schema"]),
            target_name=str(values["target_name"]),
            physical_generation_id=str(values["physical_generation_id"]),
            virtual_environment_name=MicrobatchEventCodec._optional_str(
                values["virtual_environment_name"]
            ),
            virtual_model_version_hash=MicrobatchEventCodec._optional_str(
                values["virtual_model_version_hash"]
            ),
        )

        return MicrobatchEvent(
            event_id=str(values["event_id"]),
            record_type=MicrobatchRecordType(values["record_type"]),
            scope=scope,
            origin_run_id=str(values["origin_run_id"]),
            execution_run_id=str(values["execution_run_id"]),
            run_type=MicrobatchRunType(values["run_type"]),
            run_start=str(values["run_start"]),
            run_end=str(values["run_end"]),
            batch_size=str(values["batch_size"]),
            cursor_column=str(values["cursor_column"]),
            cursor_type=str(values["cursor_type"]),
            model_version_hash=MicrobatchEventCodec._optional_str(values["model_version_hash"]),
            definition_hash=MicrobatchEventCodec._optional_str(values["definition_hash"]),
            fingerprint_status=MicrobatchFingerprintStatus(values["fingerprint_status"]),
            created_at=MicrobatchEventCodec._datetime(values["created_at"]),
            origin_run_started_at=MicrobatchEventCodec._optional_datetime(
                values["origin_run_started_at"]
            ),
            execution_run_started_at=MicrobatchEventCodec._optional_datetime(
                values["execution_run_started_at"]
            ),
            cursor_grain=MicrobatchEventCodec._optional_str(values["cursor_grain"]),
            completion_type=MicrobatchEventCodec._optional_completion_type(
                values["completion_type"]
            ),
            partition_start=MicrobatchEventCodec._optional_str(values["partition_start"]),
            partition_end=MicrobatchEventCodec._optional_str(values["partition_end"]),
            replay_requirement_id=MicrobatchEventCodec._optional_str(
                values["replay_requirement_id"]
            ),
            required_model_version_hash=MicrobatchEventCodec._optional_str(
                values["required_model_version_hash"]
            ),
            previous_model_version_hash=MicrobatchEventCodec._optional_str(
                values["previous_model_version_hash"]
            ),
            replay_policy=MicrobatchEventCodec._optional_str(values["replay_policy"]),
            rows_affected=MicrobatchEventCodec._optional_int(values["rows_affected"]),
            completed_at=MicrobatchEventCodec._optional_datetime(values["completed_at"]),
            coverage_source=MicrobatchEventCodec._optional_str(values["coverage_source"]),
            observed_row_count=MicrobatchEventCodec._optional_int(values["observed_row_count"]),
            observed_at=MicrobatchEventCodec._optional_datetime(values["observed_at"]),
            synthetic_reason=MicrobatchEventCodec._optional_str(values["synthetic_reason"]),
            unaccounted_policy=MicrobatchEventCodec._optional_policy(values["unaccounted_policy"]),
        )

    @staticmethod
    def from_rows(rows: Iterable[tuple[Any, ...]]) -> tuple[MicrobatchEvent, ...]:
        """Decode active events while ignoring explicitly retired record types."""

        return tuple(
            MicrobatchEventCodec.from_row(row)
            for row in rows
            if str(row[_RECORD_TYPE_COLUMN_INDEX]) not in RETIRED_MICROBATCH_RECORD_TYPES
        )

    @staticmethod
    def _optional_str(value: object) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return None if value is None else int(str(value))

    @staticmethod
    def _datetime(value: object) -> datetime:
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))

    @staticmethod
    def _optional_datetime(value: object) -> datetime | None:
        return None if value is None else MicrobatchEventCodec._datetime(value)

    @staticmethod
    def _optional_completion_type(value: object) -> MicrobatchCompletionType | None:
        return None if value is None else MicrobatchCompletionType(value)

    @staticmethod
    def _optional_policy(value: object) -> UnaccountedPartitionPolicy | None:
        return None if value is None else UnaccountedPartitionPolicy(value)
