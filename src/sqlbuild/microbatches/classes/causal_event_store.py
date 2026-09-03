"""Typed facade for causal facts in a shared microbatch event store."""

from __future__ import annotations

from sqlbuild.microbatches.classes.causal_event_codec import CausalEventCodec
from sqlbuild.microbatches.models import (
    ConsumerFrontier,
    MicrobatchEvent,
    MicrobatchScope,
    MicrobatchWriteResult,
    ProducerCompletion,
)
from sqlbuild.microbatches.types import MicrobatchEventStore, MicrobatchRecordType


class CausalMicrobatchEventStore:
    """Persist and retrieve typed causal records through any microbatch store."""

    def __init__(self, store: MicrobatchEventStore) -> None:
        self._store = store

    def write(self, record: ProducerCompletion | ConsumerFrontier) -> None:
        self._store.write(CausalEventCodec.to_event(record))

    def write_many(
        self, records: tuple[ProducerCompletion | ConsumerFrontier, ...]
    ) -> MicrobatchWriteResult:
        return self._store.write_many(
            tuple(CausalEventCodec.to_event(record) for record in records)
        )

    def read_producer_completions(
        self, producer_scope: MicrobatchScope
    ) -> tuple[ProducerCompletion, ...]:
        events: tuple[MicrobatchEvent, ...] = self._store.read_scope_history(producer_scope)
        return tuple(
            record
            for event in events
            if event.record_type == MicrobatchRecordType.PRODUCER_COMPLETION
            and isinstance((record := CausalEventCodec.from_event(event)), ProducerCompletion)
        )

    def read_consumer_frontiers(
        self, consumer_scope: MicrobatchScope
    ) -> tuple[ConsumerFrontier, ...]:
        events: tuple[MicrobatchEvent, ...] = self._store.read_scope_history(consumer_scope)
        return tuple(
            record
            for event in events
            if event.record_type == MicrobatchRecordType.CONSUMER_FRONTIER
            and isinstance((record := CausalEventCodec.from_event(event)), ConsumerFrontier)
        )
