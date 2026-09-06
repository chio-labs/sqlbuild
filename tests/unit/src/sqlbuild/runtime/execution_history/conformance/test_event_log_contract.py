"""Reusable event log storage conformance harness."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast

import pytest

from sqlbuild.execution_history import (
    EventFamily,
    EventFilter,
    EventPage,
    IntegrityConflictError,
    InvalidCursorError,
    InvalidEventError,
    InvalidLimitError,
    LifecycleEventLogStorage,
    StoredEvent,
    canonical_event_content,
    canonical_event_id,
)
from sqlbuild.runtime.observability.models import LifecycleEvent, OpaqueLifecycleEvent
from tests.unit.src.sqlbuild.runtime.execution_history.conformance._test_types import (
    ContractCase,
    FilterCase,
    LimitCase,
    OpaqueIdCase,
    PagingCase,
)
from tests.unit.src.sqlbuild.runtime.execution_history.conformance.helpers import (
    BASE_TIME,
    invocation_event,
    lifecycle_event,
    opaque_event,
    opaque_from_known,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PagingCase(
            description="single-record pages preserve every durable fact",
            page_size=1,
            expected_event_ids=("event-1", "event-2", "event-3", "event-4", "event-5"),
        ),
        PagingCase(
            description="uneven pages preserve every durable fact",
            page_size=2,
            expected_event_ids=("event-1", "event-2", "event-3", "event-4", "event-5"),
        ),
        PagingCase(
            description="oversized page preserves every durable fact",
            page_size=10,
            expected_event_ids=("event-1", "event-2", "event-3", "event-4", "event-5"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_durable_events_when_paging_exclusively_then_no_gaps_or_duplicates_occur(
    event_log: LifecycleEventLogStorage, test_case: PagingCase
) -> None:
    events: tuple[LifecycleEvent, ...] = tuple(
        lifecycle_event(f"event-{index}", run_id=f"run-{index}") for index in range(1, 6)
    )
    _ = event_log.append_events(events)
    cursor: str | None = None
    collected: list[str] = []
    has_more = True

    while has_more:
        page: EventPage = event_log.get_events(
            event_filter=EventFilter(), after_cursor=cursor, limit=test_case.page_size
        )
        collected.extend(cast(LifecycleEvent, record.event).event_id for record in page.records)
        cursor = page.next_cursor
        has_more = page.has_more

    assert tuple(collected) == test_case.expected_event_ids


@pytest.mark.parametrize(
    "test_case",
    [
        FilterCase(
            description="invocation correlation",
            event_filter=EventFilter(invocation_id="invocation-2"),
            expected_event_ids=("event-2",),
        ),
        FilterCase(
            description="run correlation",
            event_filter=EventFilter(run_id="run-2"),
            expected_event_ids=("event-2",),
        ),
        FilterCase(
            description="exact event types",
            event_filter=EventFilter(event_types=("run_completed",)),
            expected_event_ids=("event-2",),
        ),
        FilterCase(
            description="event family",
            event_filter=EventFilter(family=EventFamily.INVOCATION),
            expected_event_ids=("event-3",),
        ),
        FilterCase(
            description="producer",
            event_filter=EventFilter(producer="extension"),
            expected_event_ids=("event-2",),
        ),
        FilterCase(
            description="inclusive occurred-at range",
            event_filter=EventFilter(
                occurred_at_start=BASE_TIME + timedelta(seconds=1),
                occurred_at_end=BASE_TIME + timedelta(seconds=1),
            ),
            expected_event_ids=("event-2",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_durable_events_when_filtering_then_only_domain_matches_are_returned(
    event_log: LifecycleEventLogStorage, test_case: FilterCase
) -> None:
    _ = event_log.append_events(
        (
            lifecycle_event("event-1", run_id="run-1"),
            lifecycle_event(
                "event-2",
                "run_completed",
                invocation_id="invocation-2",
                run_id="run-2",
                producer="extension",
                occurred_at=BASE_TIME + timedelta(seconds=1),
            ),
            invocation_event("event-3"),
        )
    )

    page: EventPage = event_log.get_events(event_filter=test_case.event_filter, limit=100)

    assert (
        tuple(cast(LifecycleEvent, record.event).event_id for record in page.records)
        == test_case.expected_event_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="event filters compose with inclusive time boundaries", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_events_when_composing_correlations_type_producer_and_time_range_then_only_boundary_match_returns(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    boundary: datetime = BASE_TIME + timedelta(seconds=1)
    _ = event_log.append_events(
        (
            lifecycle_event(
                "match",
                "run_completed",
                invocation_id="selected-invocation",
                run_id="selected-run",
                producer="selected-producer",
                occurred_at=boundary,
            ),
            lifecycle_event("other", "run_completed", run_id="selected-run", occurred_at=boundary),
        )
    )

    page: EventPage = event_log.get_events(
        event_filter=EventFilter(
            invocation_id="selected-invocation",
            run_id="selected-run",
            event_types=("run_completed",),
            producer="selected-producer",
            occurred_at_start=boundary,
            occurred_at_end=boundary,
        )
    )

    assert len(page.records) == test_case.expected_count
    assert canonical_event_id(page.records[0].event) == "match"


@pytest.mark.parametrize(
    "test_case",
    [
        FilterCase(
            description="opaque event type uses typed envelope field",
            event_filter=EventFilter(event_types=("run_started",)),
            expected_event_ids=("opaque-match",),
        ),
        FilterCase(
            description="opaque producer uses typed envelope field",
            event_filter=EventFilter(producer="opaque-producer"),
            expected_event_ids=("opaque-match",),
        ),
        FilterCase(
            description="opaque invocation uses typed envelope field",
            event_filter=EventFilter(invocation_id="opaque-invocation"),
            expected_event_ids=("opaque-match",),
        ),
        FilterCase(
            description="opaque run uses typed envelope field",
            event_filter=EventFilter(run_id="opaque-run"),
            expected_event_ids=("opaque-match",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_opaque_envelopes_when_filtering_then_only_correctly_typed_stable_fields_match(
    event_log: LifecycleEventLogStorage, test_case: FilterCase
) -> None:
    matching: OpaqueLifecycleEvent = opaque_event("opaque-match")
    malformed: OpaqueLifecycleEvent = opaque_event(
        "opaque-malformed",
        event_type=7,
        producer=7,
        invocation_id=7,
        run_id=7,
    )
    _ = event_log.append_events((matching, malformed))

    page: EventPage = event_log.get_events(event_filter=test_case.event_filter)

    assert tuple(canonical_event_id(record.event) for record in page.records) == (
        test_case.expected_event_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="unfiltered query retains malformed opaque envelope", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_opaque_envelope_missing_filter_fields_when_querying_without_filter_then_it_is_returned(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    opaque: OpaqueLifecycleEvent = OpaqueLifecycleEvent(
        raw={"event_id": "minimal-opaque", "schema_version": 2}
    )
    _ = event_log.append_event(opaque)

    page: EventPage = event_log.get_events(event_filter=EventFilter())

    assert len(page.records) == test_case.expected_count
    assert canonical_event_id(page.records[0].event) == "minimal-opaque"


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="empty result has no cursor and no continuation", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_no_matching_events_when_reading_then_empty_page_has_no_cursor(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    page: EventPage = event_log.get_events(event_filter=EventFilter(run_id="absent"), limit=100)

    assert len(page.records) == test_case.expected_count
    assert page.next_cursor is None
    assert page.has_more is False


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="equivalent duplicate keeps one durable fact", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_equivalent_event_id_when_appending_twice_then_second_append_is_noop(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    event: LifecycleEvent = lifecycle_event("same-event")

    first: StoredEvent = event_log.append_event(event)
    second: StoredEvent = event_log.append_event(event)
    page: EventPage = event_log.get_events(event_filter=EventFilter(), limit=100)

    assert second == first
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="conflict leaves original durable fact untouched", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_conflicting_event_id_when_appending_then_conflict_does_not_mutate_log(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    original: LifecycleEvent = lifecycle_event("same-event")
    conflicting: LifecycleEvent = replace(original, producer="different-producer")
    first: StoredEvent = event_log.append_event(original)

    with pytest.raises(IntegrityConflictError):
        event_log.append_event(conflicting)

    page: EventPage = event_log.get_events(event_filter=EventFilter(), limit=100)
    assert page.records == (first,)
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="conflicting batch is atomic", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_conflicting_event_id_within_batch_when_appending_then_no_fact_is_mutated(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    original: LifecycleEvent = lifecycle_event("same-event")
    conflicting: LifecycleEvent = replace(original, producer="different-producer")

    with pytest.raises(IntegrityConflictError):
        event_log.append_events((original, conflicting))

    page: EventPage = event_log.get_events(event_filter=EventFilter(), limit=100)
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="late conflict makes mixed batch atomic", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_preexisting_event_and_fresh_then_conflicting_batch_when_appending_then_fresh_fact_is_not_committed(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    original: LifecycleEvent = lifecycle_event("preexisting")
    _ = event_log.append_event(original)
    fresh: LifecycleEvent = lifecycle_event("fresh", run_id="run-fresh")
    conflicting: LifecycleEvent = replace(original, producer="different-producer")

    with pytest.raises(IntegrityConflictError):
        event_log.append_events((fresh, conflicting))

    page: EventPage = event_log.get_events(event_filter=EventFilter())
    assert len(page.records) == test_case.expected_count
    assert cast(LifecycleEvent, page.records[0].event).event_id == "preexisting"


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="known and opaque equivalent content retry is a no-op", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_known_event_represented_opaquely_when_retrying_then_canonical_content_is_equivalent(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    known: LifecycleEvent = lifecycle_event("equivalent")
    opaque: OpaqueLifecycleEvent = opaque_from_known(known)

    first: StoredEvent = event_log.append_event(known)
    second: StoredEvent = event_log.append_event(opaque)

    assert canonical_event_id(opaque) == known.event_id
    assert canonical_event_content(opaque) == canonical_event_content(known)
    assert second == first
    assert first.storage_order == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="conflicting opaque reuse keeps original", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_opaque_event_id_reused_with_different_content_when_appending_then_conflict_preserves_original(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    original: OpaqueLifecycleEvent = opaque_event("opaque-id", producer="producer-a")
    conflicting: OpaqueLifecycleEvent = opaque_event("opaque-id", producer="producer-b")
    first: StoredEvent = event_log.append_event(original)

    with pytest.raises(IntegrityConflictError):
        event_log.append_event(conflicting)

    page: EventPage = event_log.get_events(event_filter=EventFilter())
    assert page.records == (first,)
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="opaque and known same ID with different content conflict", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_opaque_then_known_same_id_with_different_content_when_appending_then_conflict_is_raised(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    opaque: OpaqueLifecycleEvent = opaque_event("shared-id")
    known: LifecycleEvent = lifecycle_event("shared-id")
    _ = event_log.append_event(opaque)

    with pytest.raises(IntegrityConflictError):
        event_log.append_event(known)

    page: EventPage = event_log.get_events(event_filter=EventFilter())
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="opaque conflict makes mixed batch atomic", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_preexisting_opaque_and_fresh_then_conflicting_opaque_batch_when_appending_then_batch_is_atomic(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    original: OpaqueLifecycleEvent = opaque_event("opaque-existing", producer="producer-a")
    _ = event_log.append_event(original)
    fresh: OpaqueLifecycleEvent = opaque_event("opaque-fresh")
    conflicting: OpaqueLifecycleEvent = opaque_event("opaque-existing", producer="producer-b")

    with pytest.raises(IntegrityConflictError):
        event_log.append_events((fresh, conflicting))

    page: EventPage = event_log.get_events(event_filter=EventFilter())
    assert len(page.records) == test_case.expected_count
    assert canonical_event_id(page.records[0].event) == "opaque-existing"


@pytest.mark.parametrize(
    "test_case",
    [
        OpaqueIdCase(
            description="empty opaque event ID is invalid",
            event_id="",
            expected_error="non-empty string event_id",
        ),
        OpaqueIdCase(
            description="non-string opaque event ID is invalid",
            event_id=7,
            expected_error="non-empty string event_id",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_opaque_envelope_without_valid_event_id_when_appending_then_event_is_rejected(
    event_log: LifecycleEventLogStorage, test_case: OpaqueIdCase
) -> None:
    malformed: OpaqueLifecycleEvent = OpaqueLifecycleEvent(
        raw={"schema_version": 2, "event_id": test_case.event_id}
    )

    with pytest.raises(InvalidEventError, match=test_case.expected_error):
        event_log.append_event(malformed)

    page: EventPage = event_log.get_events(event_filter=EventFilter())
    assert page.records == ()


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="whole batch retry keeps one fact per event ID", expected_count=3)],
    ids=lambda case: case.description,
)
def test_given_successful_batch_when_retrying_same_batch_then_no_duplicate_facts_exist(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    events: tuple[LifecycleEvent, ...] = tuple(
        lifecycle_event(f"batch-{index}", run_id=f"run-{index}") for index in range(3)
    )

    first: tuple[StoredEvent, ...] = event_log.append_events(events)
    second: tuple[StoredEvent, ...] = event_log.append_events(events)
    page: EventPage = event_log.get_events(event_filter=EventFilter(), limit=100)

    assert second == first
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        LimitCase(description="zero is rejected", limit=0, expected_error="1 through 1000"),
        LimitCase(
            description="over maximum is rejected", limit=1001, expected_error="1 through 1000"
        ),
        LimitCase(description="boolean is rejected", limit=True, expected_error="1 through 1000"),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_page_limit_when_reading_then_contract_error_is_raised(
    event_log: LifecycleEventLogStorage, test_case: LimitCase
) -> None:
    with pytest.raises(InvalidLimitError, match=test_case.expected_error):
        event_log.get_events(
            event_filter=EventFilter(),
            limit=test_case.limit,  # ty: ignore[invalid-argument-type]
        )


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="factory returns independent contract backend", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_backend_factory_when_constructing_storage_then_contract_is_reusable(
    event_log_factory: Callable[[], LifecycleEventLogStorage], test_case: ContractCase
) -> None:
    storage: LifecycleEventLogStorage = event_log_factory()

    page: EventPage = storage.get_events(event_filter=EventFilter(), limit=1)
    storage.dispose()

    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="event cursor remains valid when filter changes", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_global_event_cursor_when_changing_filter_then_exclusive_position_remains_valid(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    _ = event_log.append_events(
        (
            lifecycle_event("first", invocation_id="other"),
            lifecycle_event("second", invocation_id="selected"),
        )
    )
    first: EventPage = event_log.get_events(event_filter=EventFilter(), limit=1)

    filtered: EventPage = event_log.get_events(
        event_filter=EventFilter(invocation_id="selected"),
        after_cursor=first.next_cursor,
        limit=1,
    )

    assert len(filtered.records) == test_case.expected_count
    assert canonical_event_id(filtered.records[0].event) == "second"


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="filtered event pagination has no gaps or duplicates", expected_count=2
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interleaved_events_when_paging_filtered_results_then_global_cursor_is_exclusive_without_gaps(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    _ = event_log.append_events(
        (
            lifecycle_event("selected-1", invocation_id="selected"),
            lifecycle_event("other", invocation_id="other"),
            lifecycle_event("selected-2", invocation_id="selected"),
        )
    )
    event_filter: EventFilter = EventFilter(invocation_id="selected")
    first: EventPage = event_log.get_events(event_filter=event_filter, limit=1)
    second: EventPage = event_log.get_events(
        event_filter=event_filter, after_cursor=first.next_cursor, limit=1
    )
    event_ids: tuple[str, ...] = tuple(
        canonical_event_id(record.event) for record in first.records + second.records
    )

    assert event_ids == ("selected-1", "selected-2")
    assert len(set(event_ids)) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="malformed event cursor is rejected", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_invalid_or_foreign_event_cursor_when_reading_then_cursor_error_is_raised(
    event_log: LifecycleEventLogStorage, test_case: ContractCase
) -> None:
    _ = event_log.append_event(lifecycle_event("only"))

    with pytest.raises(InvalidCursorError):
        event_log.get_events(
            event_filter=EventFilter(), after_cursor=f"invalid:{test_case.description}"
        )

    assert test_case.expected_count == 0


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="foreign event cursor is rejected", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_cursor_from_other_event_log_when_reading_then_foreign_cursor_is_rejected(
    event_log: LifecycleEventLogStorage,
    event_log_factory: Callable[[], LifecycleEventLogStorage],
    test_case: ContractCase,
) -> None:
    _ = event_log.append_event(lifecycle_event("local"))
    foreign: LifecycleEventLogStorage = event_log_factory()
    _ = foreign.append_event(lifecycle_event("foreign"))
    foreign_page: EventPage = foreign.get_events(event_filter=EventFilter(), limit=1)

    with pytest.raises(InvalidCursorError):
        event_log.get_events(event_filter=EventFilter(), after_cursor=foreign_page.next_cursor)

    assert test_case.expected_count == 0
