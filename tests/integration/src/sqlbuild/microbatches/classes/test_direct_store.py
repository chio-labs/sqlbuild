"""Integration coverage for direct microbatch bulk event publication."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.microbatches.classes.direct_store import DirectMicrobatchEventStore
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from tests.integration.src.sqlbuild.microbatches.classes._test_types import (
    DirectStorePublicationTestCase,
    DirectStoreSuccessiveWriteTestCase,
    RetiredDirectStoreRecordTestCase,
)
from tests.integration.src.sqlbuild.microbatches.classes.helpers import (
    build_events,
    insert_raw_event_record_type,
)


class _RecordingDuckDbAdapter(DuckDbAdapter):
    def __init__(self) -> None:
        self.statement_recorder = StatementRecorder()

    def _execute(self, *, connection: Any, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return super()._execute(connection=connection, sql=sql)


@pytest.mark.parametrize(
    "test_case",
    (
        RetiredDirectStoreRecordTestCase(
            description="producer completion row",
            retired_record_type="producer_completion",
            expected_event_count=1,
        ),
        RetiredDirectStoreRecordTestCase(
            description="consumer frontier row",
            retired_record_type="consumer_frontier",
            expected_event_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_retired_rows_when_reading_direct_history_then_only_active_events_are_returned(
    test_case: RetiredDirectStoreRecordTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    store: DirectMicrobatchEventStore = DirectMicrobatchEventStore(
        adapter=adapter, connection=connection
    )
    try:
        active: MicrobatchEvent = build_events(count=1)[0]
        store.write(active)
        retired: MicrobatchEvent = build_events(count=1, start_at=1)[0]
        insert_raw_event_record_type(
            connection=connection,
            event=retired,
            record_type=test_case.retired_record_type,
        )

        scope: MicrobatchScope = active.scope
        history: tuple[MicrobatchEvent, ...] = store.read_scope_history(scope)

        assert len(history) == test_case.expected_event_count
        assert tuple(event.event_id for event in history) == (active.event_id,)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectStorePublicationTestCase(
            description="one thousand events use four bulk chunks",
            event_count=1000,
            expected_total=1000,
            expected_inserted=1000,
            expected_already_existing=0,
            expected_statement_count=14,
        ),
        DirectStorePublicationTestCase(
            description="exact chunk boundary uses one bulk chunk",
            event_count=250,
            expected_total=250,
            expected_inserted=250,
            expected_already_existing=0,
            expected_statement_count=8,
        ),
        DirectStorePublicationTestCase(
            description="one event beyond chunk boundary uses two bulk chunks",
            event_count=251,
            expected_total=251,
            expected_inserted=251,
            expected_already_existing=0,
            expected_statement_count=10,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fresh_events_when_bulk_publishing_then_statements_are_bounded_and_counts_are_exact(
    test_case: DirectStorePublicationTestCase,
) -> None:
    adapter: _RecordingDuckDbAdapter = _RecordingDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    store: DirectMicrobatchEventStore = DirectMicrobatchEventStore(
        adapter=adapter, connection=connection
    )
    events: tuple[MicrobatchEvent, ...] = build_events(count=test_case.event_count)
    try:
        result: MicrobatchWriteResult = store.write_many(events)
        statements: tuple[str, ...] = tuple(
            event.content for event in adapter.statement_recorder.snapshot()
        )

        assert result.total == test_case.expected_total
        assert result.inserted == test_case.expected_inserted
        assert result.already_existing == test_case.expected_already_existing
        assert len(statements) == test_case.expected_statement_count
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectStorePublicationTestCase(
            description="republication performs four lookups and no inserts",
            event_count=1000,
            expected_total=1000,
            expected_inserted=0,
            expected_already_existing=1000,
            expected_statement_count=4,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_published_events_when_republishing_then_only_existing_id_lookups_execute(
    test_case: DirectStorePublicationTestCase,
) -> None:
    adapter: _RecordingDuckDbAdapter = _RecordingDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    store: DirectMicrobatchEventStore = DirectMicrobatchEventStore(
        adapter=adapter, connection=connection
    )
    events: tuple[MicrobatchEvent, ...] = build_events(count=test_case.event_count)
    try:
        store.write_many(events)
        adapter.statement_recorder.events.clear()

        result: MicrobatchWriteResult = store.write_many(events)
        statements: tuple[str, ...] = tuple(
            event.content for event in adapter.statement_recorder.snapshot()
        )

        assert result.total == test_case.expected_total
        assert result.inserted == test_case.expected_inserted
        assert result.already_existing == test_case.expected_already_existing
        assert len(statements) == test_case.expected_statement_count
        assert all(statement.startswith("SELECT event_id") for statement in statements)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectStoreSuccessiveWriteTestCase(
            description="successive writes initialize state once per store",
            initial_event_count=250,
            successive_event_count=1,
            expected_initial_statement_count=8,
            expected_successive_statement_count=2,
            expected_initialization_statement_count=6,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_initialized_store_when_publishing_more_events_then_initialization_is_not_repeated(
    test_case: DirectStoreSuccessiveWriteTestCase,
) -> None:
    adapter: _RecordingDuckDbAdapter = _RecordingDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    store: DirectMicrobatchEventStore = DirectMicrobatchEventStore(
        adapter=adapter, connection=connection
    )
    initial_events: tuple[MicrobatchEvent, ...] = build_events(count=test_case.initial_event_count)
    successive_events: tuple[MicrobatchEvent, ...] = build_events(
        count=test_case.successive_event_count, start_at=test_case.initial_event_count
    )
    try:
        store.write_many(initial_events)
        initial_statements: tuple[str, ...] = tuple(
            event.content for event in adapter.statement_recorder.snapshot()
        )
        adapter.statement_recorder.events.clear()

        store.write_many(successive_events)
        successive_statements: tuple[str, ...] = tuple(
            event.content for event in adapter.statement_recorder.snapshot()
        )
        initialization_statements: tuple[str, ...] = initial_statements[
            : test_case.expected_initialization_statement_count
        ]

        assert len(initial_statements) == test_case.expected_initial_statement_count
        assert len(successive_statements) == test_case.expected_successive_statement_count
        assert len(initialization_statements) == test_case.expected_initialization_statement_count
        assert all(statement.startswith("CREATE") for statement in initialization_statements)
        assert all(not statement.startswith("CREATE") for statement in successive_statements)
    finally:
        adapter.close(connection)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
