"""Unit coverage for causal microbatch event primitives."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from sqlbuild.compiler.planner.models import CursorInputRelation
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.microbatches._helpers.causal_event_identity import consumer_frontier_event_id
from sqlbuild.microbatches._helpers.causal_projection import (
    project_outstanding_producer_completions,
    snapshot_producer_completions,
)
from sqlbuild.microbatches.classes.causal_event_codec import CausalEventCodec
from sqlbuild.microbatches.main._causal_input_relations import resolve_causal_input_relations
from sqlbuild.microbatches.main.project_coverage import project_microbatch_coverage
from sqlbuild.microbatches.models import (
    ConsumedProducerInterval,
    ConsumerFrontier,
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
    OutstandingProducerCompletions,
    ProducerCompletion,
    ProducerCompletionSnapshot,
)
from sqlbuild.microbatches.types import CausalHistoryStatus, MicrobatchRecordType
from tests.unit.src.sqlbuild.microbatches._test_types import (
    CausalEventTestCase,
    CausalInputGrainTestCase,
)
from tests.unit.src.sqlbuild.microbatches.helpers import (
    CAUSAL_CREATED_AT,
    CONSUMER_SCOPE,
    PRODUCER_SCOPE,
    causal_completion,
    causal_completion_id,
    causal_dependency,
    causal_frontier,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CausalInputGrainTestCase(
            description="known current dependency uses declared consumer grain",
            dependency=causal_dependency(history_status=CausalHistoryStatus.KNOWN, intervals=()),
            expected_grain="day",
        ),
        CausalInputGrainTestCase(
            description="known outstanding dependency uses producer grain",
            dependency=causal_dependency(
                history_status=CausalHistoryStatus.KNOWN,
                intervals=(MicrobatchInterval("2026-07-01", "2026-08-01"),),
            ),
            expected_grain="month",
        ),
        CausalInputGrainTestCase(
            description="unknown history retains conservative producer grain",
            dependency=causal_dependency(history_status=CausalHistoryStatus.UNKNOWN, intervals=()),
            expected_grain="month",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_causal_history_when_resolving_input_grain_then_certainty_controls_coarsening(
    test_case: CausalInputGrainTestCase,
) -> None:
    relation: CursorInputRelation = CursorInputRelation(
        relation="main.upstream",
        cursor_column="event_time",
        cursor_grain="month",
        producer_model_name="upstream",
        is_model_backed=True,
    )

    result: tuple[CursorInputRelation, ...] = resolve_causal_input_relations(
        relations=(relation,),
        downstream_grain="day",
        dependencies=(test_case.dependency,),
    )

    assert result[0].cursor_grain == test_case.expected_grain


@pytest.mark.parametrize(
    "test_case",
    [CausalEventTestCase(description="causal codec", expected_enabled=True)],
    ids=lambda case: case.description,
)
def test_given_causal_records_when_round_tripping_codec_then_all_semantics_are_preserved(
    test_case: CausalEventTestCase,
) -> None:
    completion: ProducerCompletion = causal_completion(
        event_id="producer-event", start="2026-07-01", end="2026-08-01"
    )
    frontier: ConsumerFrontier = causal_frontier(
        captured=frozenset({completion.event_id}), event_id="frontier-event"
    )

    completion_event: MicrobatchEvent = CausalEventCodec.to_event(completion)
    frontier_event: MicrobatchEvent = CausalEventCodec.to_event(frontier)

    assert CausalEventCodec.from_event(completion_event) == completion
    assert CausalEventCodec.from_event(frontier_event) == frontier
    assert completion_event.record_type == MicrobatchRecordType.PRODUCER_COMPLETION
    assert frontier_event.record_type == MicrobatchRecordType.CONSUMER_FRONTIER
    assert '"schema":"sqlbuild.microbatch.causal/v1"' in (frontier_event.coverage_source or "")
    assert frontier_event.replay_requirement_id is None
    assert frontier_event.synthetic_reason is None
    assert test_case.expected_enabled


@pytest.mark.parametrize(
    "test_case",
    [CausalEventTestCase(description="causal identity", expected_enabled=True)],
    ids=lambda case: case.description,
)
def test_given_same_retry_and_distinct_runs_when_identifying_completion_then_only_retry_deduplicates(
    test_case: CausalEventTestCase,
) -> None:
    first: str = causal_completion_id(producer_run_id="run-1")
    retry: str = causal_completion_id(producer_run_id="run-1")
    later_run: str = causal_completion_id(producer_run_id="run-2")
    first_frontier: str = consumer_frontier_event_id(
        consumer_scope=CONSUMER_SCOPE,
        consumer_model_version_hash="consumer-v1",
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
        captured_producer_event_ids=frozenset({"U5", "U4"}),
        consumer_run_id="consumer-run",
    )
    reordered_frontier: str = consumer_frontier_event_id(
        consumer_scope=CONSUMER_SCOPE,
        consumer_model_version_hash="consumer-v1",
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
        captured_producer_event_ids=frozenset({"U4", "U5"}),
        consumer_run_id="consumer-run",
    )

    assert first == retry
    assert first != later_run
    assert first_frontier == reordered_frontier
    assert test_case.expected_enabled


@pytest.mark.parametrize(
    "test_case",
    [CausalEventTestCase(description="post-snapshot completion", expected_enabled=True)],
    ids=lambda case: case.description,
)
def test_given_acknowledged_snapshot_and_post_snapshot_completion_when_projecting_then_later_event_remains_outstanding(
    test_case: CausalEventTestCase,
) -> None:
    first: ProducerCompletion = causal_completion(
        event_id="U4", start="2026-07-01", end="2026-08-01"
    )
    later: ProducerCompletion = causal_completion(
        event_id="U5",
        start="2026-08-01",
        end="2026-09-01",
        created_at=CAUSAL_CREATED_AT - timedelta(days=1),
    )
    captured: ProducerCompletionSnapshot = snapshot_producer_completions(
        completions=(first,),
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
    )
    frontier: ConsumerFrontier = causal_frontier(captured=captured.event_ids, event_id="D4")
    next_snapshot: ProducerCompletionSnapshot = snapshot_producer_completions(
        completions=(first, later),
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
    )

    projection: OutstandingProducerCompletions = project_outstanding_producer_completions(
        snapshot=next_snapshot,
        frontiers=(frontier,),
        consumer_scope=CONSUMER_SCOPE,
        consumer_model_version_hash="consumer-v1",
        cursor_type=CursorType.TIMESTAMP,
    )

    assert tuple(completion.event_id for completion in projection.completions) == ("U5",)
    assert projection.intervals == (MicrobatchInterval("2026-08-01", "2026-09-01"),)
    assert test_case.expected_enabled


@pytest.mark.parametrize(
    "test_case",
    [CausalEventTestCase(description="clipped disjoint consumption", expected_enabled=True)],
    ids=lambda case: case.description,
)
def test_given_partial_disjoint_consumption_when_projecting_then_only_exact_remainders_stay_outstanding(
    test_case: CausalEventTestCase,
) -> None:
    completion: ProducerCompletion = causal_completion(
        event_id="U4", start="2026-07-01", end="2026-07-06"
    )
    snapshot: ProducerCompletionSnapshot = snapshot_producer_completions(
        completions=(completion,),
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
    )
    frontier: ConsumerFrontier = causal_frontier(
        captured=frozenset(),
        event_id="D4",
        consumed=(
            ConsumedProducerInterval("U4", MicrobatchInterval("2026-07-01", "2026-07-02")),
            ConsumedProducerInterval("U4", MicrobatchInterval("2026-07-04", "2026-07-05")),
        ),
    )

    projection: OutstandingProducerCompletions = project_outstanding_producer_completions(
        snapshot=snapshot,
        frontiers=(frontier,),
        consumer_scope=CONSUMER_SCOPE,
        consumer_model_version_hash="consumer-v1",
        cursor_type=CursorType.TIMESTAMP,
    )

    assert projection.intervals == (
        MicrobatchInterval("2026-07-02", "2026-07-04"),
        MicrobatchInterval("2026-07-05", "2026-07-06"),
    )
    assert projection.acknowledged_event_ids == frozenset()
    assert test_case.expected_enabled


@pytest.mark.parametrize(
    "test_case",
    [CausalEventTestCase(description="generation and interval isolation", expected_enabled=True)],
    ids=lambda case: case.description,
)
def test_given_other_generations_and_overlapping_events_when_projecting_then_scope_is_exact_and_intervals_merge(
    test_case: CausalEventTestCase,
) -> None:
    completions: tuple[ProducerCompletion, ...] = (
        causal_completion(event_id="U1", start="2026-07-01", end="2026-08-01"),
        causal_completion(event_id="U2", start="2026-07-15", end="2026-08-15"),
        causal_completion(event_id="U3", start="2026-09-01", end="2026-10-01"),
        replace(
            causal_completion(event_id="old", start="2025-01-01", end="2025-02-01"),
            producer_scope=replace(
                PRODUCER_SCOPE, physical_generation_id="producer-generation-old"
            ),
        ),
    )
    snapshot: ProducerCompletionSnapshot = snapshot_producer_completions(
        completions=completions,
        producer_scope=PRODUCER_SCOPE,
        producer_model_version_hash="producer-v1",
    )

    projection: OutstandingProducerCompletions = project_outstanding_producer_completions(
        snapshot=snapshot,
        frontiers=(),
        consumer_scope=CONSUMER_SCOPE,
        consumer_model_version_hash="consumer-v1",
        cursor_type=CursorType.TIMESTAMP,
    )

    assert snapshot.event_ids == frozenset({"U1", "U2", "U3"})
    assert projection.intervals == (
        MicrobatchInterval("2026-07-01", "2026-08-15"),
        MicrobatchInterval("2026-09-01", "2026-10-01"),
    )
    assert test_case.expected_enabled


@pytest.mark.parametrize(
    "test_case",
    [CausalEventTestCase(description="coverage event isolation", expected_enabled=True)],
    ids=lambda case: case.description,
)
def test_given_causal_completion_when_projecting_partition_coverage_then_it_is_ignored(
    test_case: CausalEventTestCase,
) -> None:
    event: MicrobatchEvent = CausalEventCodec.to_event(
        causal_completion(event_id="U4", start="2026-07-01", end="2026-08-01")
    )

    projection: MicrobatchCoverageProjection = project_microbatch_coverage(
        events=(event,),
        expected_intervals=(MicrobatchInterval("2026-07-01", "2026-08-01"),),
        cursor_type=CursorType.TIMESTAMP,
    )

    assert projection.intervals == ()
    assert projection.unaccounted == (MicrobatchInterval("2026-07-01", "2026-08-01"),)
    assert test_case.expected_enabled


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
