"""Versioned causal payload codec for the existing microbatch event table."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import (
    ConsumedProducerInterval,
    ConsumerFrontier,
    MicrobatchEvent,
    MicrobatchInterval,
    MicrobatchScope,
    ProducerCompletion,
)
from sqlbuild.microbatches.types import (
    CausalCompletionKind,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
)

_CAUSAL_PAYLOAD_SCHEMA: str = "sqlbuild.microbatch.causal/v1"


class CausalEventCodec:
    """Encode causal records without overloading replay or synthetic event semantics."""

    @staticmethod
    def to_event(record: ProducerCompletion | ConsumerFrontier) -> MicrobatchEvent:
        if isinstance(record, ProducerCompletion):
            payload: dict[str, object] = {
                "schema": _CAUSAL_PAYLOAD_SCHEMA,
                "kind": MicrobatchRecordType.PRODUCER_COMPLETION.value,
                "completion_kind": record.completion_kind.value,
            }
            return MicrobatchEvent(
                event_id=record.event_id,
                record_type=MicrobatchRecordType.PRODUCER_COMPLETION,
                scope=record.producer_scope,
                origin_run_id=record.producer_run_id,
                execution_run_id=record.producer_run_id,
                run_type=record.run_type,
                run_start=record.interval.start,
                run_end=record.interval.end,
                batch_size="",
                cursor_column="",
                cursor_type="",
                model_version_hash=record.producer_model_version_hash,
                definition_hash=None,
                fingerprint_status=record.fingerprint_status,
                partition_start=record.interval.start,
                partition_end=record.interval.end,
                coverage_source=_canonical_payload(payload),
                created_at=record.created_at,
            )

        payload: dict[str, object] = {
            "schema": _CAUSAL_PAYLOAD_SCHEMA,
            "kind": MicrobatchRecordType.CONSUMER_FRONTIER.value,
            "producer_scope": _scope_payload(record.producer_scope),
            "producer_model_version_hash": record.producer_model_version_hash,
            "captured_producer_event_ids": sorted(record.captured_producer_event_ids),
            "consumed_intervals": [
                {
                    "producer_event_id": item.producer_event_id,
                    "start": item.interval.start,
                    "end": item.interval.end,
                }
                for item in record.consumed_intervals
            ],
        }
        return MicrobatchEvent(
            event_id=record.event_id,
            record_type=MicrobatchRecordType.CONSUMER_FRONTIER,
            scope=record.consumer_scope,
            origin_run_id=record.consumer_run_id,
            execution_run_id=record.consumer_run_id,
            run_type=MicrobatchRunType.NORMAL,
            run_start="",
            run_end="",
            batch_size="",
            cursor_column="",
            cursor_type="",
            model_version_hash=record.consumer_model_version_hash,
            definition_hash=None,
            fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
            coverage_source=_canonical_payload(payload),
            created_at=record.created_at,
        )

    @staticmethod
    def from_event(event: MicrobatchEvent) -> ProducerCompletion | ConsumerFrontier:
        if event.record_type not in {
            MicrobatchRecordType.PRODUCER_COMPLETION,
            MicrobatchRecordType.CONSUMER_FRONTIER,
        }:
            raise MicrobatchStateError(f"not a causal microbatch event: {event.record_type.value}")
        payload: dict[str, Any] = _read_payload(event.coverage_source)
        if payload.get("kind") != event.record_type.value:
            raise MicrobatchStateError("causal payload kind does not match its record type")
        if event.record_type == MicrobatchRecordType.PRODUCER_COMPLETION:
            if event.partition_start is None or event.partition_end is None:
                raise MicrobatchStateError("producer completion requires a cursor interval")
            return ProducerCompletion(
                event_id=event.event_id,
                producer_scope=event.scope,
                producer_model_version_hash=event.model_version_hash,
                interval=MicrobatchInterval(start=event.partition_start, end=event.partition_end),
                producer_run_id=event.execution_run_id,
                run_type=event.run_type,
                completion_kind=CausalCompletionKind(payload["completion_kind"]),
                fingerprint_status=event.fingerprint_status,
                created_at=event.created_at,
            )
        return ConsumerFrontier(
            event_id=event.event_id,
            consumer_scope=event.scope,
            consumer_model_version_hash=event.model_version_hash,
            producer_scope=_scope_from_payload(payload["producer_scope"]),
            producer_model_version_hash=_optional_str(payload["producer_model_version_hash"]),
            captured_producer_event_ids=frozenset(
                str(value) for value in payload["captured_producer_event_ids"]
            ),
            consumer_run_id=event.execution_run_id,
            consumed_intervals=tuple(
                ConsumedProducerInterval(
                    producer_event_id=str(item["producer_event_id"]),
                    interval=MicrobatchInterval(start=str(item["start"]), end=str(item["end"])),
                )
                for item in payload.get("consumed_intervals", ())
            ),
            created_at=event.created_at,
        )


def _canonical_payload(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _read_payload(value: str | None) -> dict[str, Any]:
    if value is None:
        raise MicrobatchStateError("causal microbatch event is missing its payload")
    payload: object = json.loads(value)
    if not isinstance(payload, dict) or payload.get("schema") != _CAUSAL_PAYLOAD_SCHEMA:
        raise MicrobatchStateError("unsupported causal microbatch payload schema")
    return cast(dict[str, Any], payload)


def _scope_payload(scope: MicrobatchScope) -> dict[str, object]:
    return {
        "scope_kind": scope.scope_kind,
        "scope_key": scope.scope_key,
        "model_name": scope.model_name,
        "target_database": scope.target_database,
        "target_schema": scope.target_schema,
        "target_name": scope.target_name,
        "physical_generation_id": scope.physical_generation_id,
        "virtual_environment_name": scope.virtual_environment_name,
        "virtual_model_version_hash": scope.virtual_model_version_hash,
    }


def _scope_from_payload(payload: object) -> MicrobatchScope:
    if not isinstance(payload, dict):
        raise MicrobatchStateError("causal producer scope must be an object")
    values: dict[str, Any] = cast(dict[str, Any], payload)
    return MicrobatchScope(
        scope_kind=str(values["scope_kind"]),
        scope_key=str(values["scope_key"]),
        model_name=str(values["model_name"]),
        target_database=_optional_str(values["target_database"]),
        target_schema=_optional_str(values["target_schema"]),
        target_name=str(values["target_name"]),
        physical_generation_id=str(values["physical_generation_id"]),
        virtual_environment_name=_optional_str(values["virtual_environment_name"]),
        virtual_model_version_hash=_optional_str(values["virtual_model_version_hash"]),
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
