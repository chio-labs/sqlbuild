"""Direct-store integration coverage for typed causal event round trips."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.microbatches.classes.causal_event_store import CausalMicrobatchEventStore
from sqlbuild.microbatches.classes.direct_store import DirectMicrobatchEventStore
from sqlbuild.microbatches.models import (
    ConsumerFrontier,
    MicrobatchInterval,
    MicrobatchScope,
    MicrobatchWriteResult,
    ProducerCompletion,
)
from sqlbuild.microbatches.types import (
    CausalCompletionKind,
    MicrobatchFingerprintStatus,
    MicrobatchRunType,
)
from tests.integration.src.sqlbuild.microbatches.classes._test_types import CausalStoreTestCase
from tests.integration.src.sqlbuild.microbatches.classes.helpers import causal_scope


@pytest.mark.parametrize(
    "test_case",
    [
        CausalStoreTestCase(
            description="idempotent causal round trip",
            expected_inserted=2,
            expected_existing=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_causal_facts_when_republishing_and_reading_direct_store_then_round_trip_is_idempotent(
    test_case: CausalStoreTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    producer_scope: MicrobatchScope = causal_scope(
        model_name="upstream", generation="producer-generation"
    )
    consumer_scope: MicrobatchScope = causal_scope(
        model_name="downstream", generation="consumer-generation"
    )
    completion: ProducerCompletion = ProducerCompletion(
        event_id="producer-U4",
        producer_scope=producer_scope,
        producer_model_version_hash="producer-v1",
        interval=MicrobatchInterval("2026-07-01", "2026-08-01"),
        producer_run_id="producer-run",
        run_type=MicrobatchRunType.NORMAL,
        completion_kind=CausalCompletionKind.PHYSICAL,
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
    )
    frontier: ConsumerFrontier = ConsumerFrontier(
        event_id="consumer-D4",
        consumer_scope=consumer_scope,
        consumer_model_version_hash="consumer-v1",
        producer_scope=producer_scope,
        producer_model_version_hash="producer-v1",
        captured_producer_event_ids=frozenset({completion.event_id}),
        consumer_run_id="consumer-run",
    )
    store: CausalMicrobatchEventStore = CausalMicrobatchEventStore(
        DirectMicrobatchEventStore(adapter=adapter, connection=connection)
    )
    try:
        first: MicrobatchWriteResult = store.write_many((completion, frontier))
        retry: MicrobatchWriteResult = store.write_many((completion, frontier))

        assert first.inserted == test_case.expected_inserted
        assert retry.inserted == 0
        assert retry.already_existing == test_case.expected_existing
        assert store.read_producer_completions(producer_scope) == (completion,)
        assert store.read_consumer_frontiers(consumer_scope) == (frontier,)
    finally:
        adapter.close(connection)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
