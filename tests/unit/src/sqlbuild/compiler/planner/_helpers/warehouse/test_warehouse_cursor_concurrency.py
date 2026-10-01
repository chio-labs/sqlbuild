"""Bounded-parallel cursor-bound reads must match sequential reads exactly."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from sqlbuild.adapter.relations.main.open_inspection_catalog import open_inspection_catalog
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import (
    _CursorModelInfo,
    _execute_cursor_queries,
    _gather_eligible_target_maxes,
    _PhysicalCursorQuery,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.types import CursorScalar
from tests.unit.src.sqlbuild.compiler.planner._helpers.warehouse._test_types import (
    ConcurrentCursorBoundsTestCase,
    EligibleTargetMaxFailureTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.warehouse.helpers import (
    ConcurrencyTrackingCursorExecute,
    EligibleMaxAdapter,
    EligibleMaxExecute,
    build_cursor_bound_queries,
    build_eligible_max_cursor_models,
)

_LATENCY_SECONDS: float = 0.01


@pytest.mark.parametrize(
    "test_case",
    [
        ConcurrentCursorBoundsTestCase(
            description="parallel reads stay within the bound",
            relation_count=24,
            concurrency=4,
            failing_relations=frozenset(),
            expected_failure_relations=(),
            expected_start_progress="Inspecting cursor bounds for 24 relations (4 concurrent)...",
        ),
        ConcurrentCursorBoundsTestCase(
            description="one failed relation stays unavailable and others succeed",
            relation_count=12,
            concurrency=8,
            failing_relations=frozenset({"analytics.raw.orders_5"}),
            expected_failure_relations=("analytics.raw.orders_5",),
            expected_start_progress="Inspecting cursor bounds for 12 relations (8 concurrent)...",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_concurrency_when_reading_cursor_bounds_then_matches_sequential_results(
    test_case: ConcurrentCursorBoundsTestCase,
) -> None:
    queries: list[_PhysicalCursorQuery] = build_cursor_bound_queries(test_case.relation_count)
    sequential_execute: ConcurrencyTrackingCursorExecute = ConcurrencyTrackingCursorExecute(
        failing_relations=test_case.failing_relations, latency_seconds=_LATENCY_SECONDS
    )
    sequential: dict[str, CursorScalar] = _execute_cursor_queries(
        queries=queries, connection=None, execute=sequential_execute, on_progress=None
    )
    parallel_execute: ConcurrencyTrackingCursorExecute = ConcurrencyTrackingCursorExecute(
        failing_relations=test_case.failing_relations, latency_seconds=_LATENCY_SECONDS
    )
    progress: list[str] = []

    parallel: dict[str, CursorScalar] = _execute_cursor_queries(
        queries=queries,
        connection=None,
        execute=parallel_execute,
        on_progress=progress.append,
        concurrency=test_case.concurrency,
    )

    failures: tuple[str, ...] = tuple(
        filter(lambda message: message.startswith("Failed"), progress)
    )
    assert list(parallel.items()) == list(sequential.items())
    assert sequential_execute.max_active == 1
    assert 1 < parallel_execute.max_active <= test_case.concurrency
    assert sorted(parallel_execute.sql) == sorted(sequential_execute.sql)
    assert len(parallel_execute.sql) == test_case.relation_count
    assert progress[0] == test_case.expected_start_progress
    assert len(progress) == test_case.relation_count + 1
    assert (
        tuple(message.split(": ")[1].split(".ordered_at")[0] for message in failures)
        == test_case.expected_failure_relations
    )


@pytest.mark.parametrize(
    "test_case",
    [
        EligibleTargetMaxFailureTestCase(
            description="failure names the model and relation",
            failing_relation="analytics.marts.orders_3",
            expected_error_fragment=(
                "model 'model_3': failed to query highest eligible target cursor for "
                "analytics.marts.orders_3.ordered_at"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_eligible_max_read_when_reading_in_parallel_then_plan_fails_naming_relation(
    test_case: EligibleTargetMaxFailureTestCase,
) -> None:
    infos: list[_CursorModelInfo] = build_eligible_max_cursor_models(6)
    results: dict[str, CursorScalar] = {
        f"model_{index}__target__max": parse(raw="2099-01-01", cursor_type=CursorType.TIMESTAMP)
        for index in range(6)
    }
    adapter: EligibleMaxAdapter = EligibleMaxAdapter()
    connection: object = object()

    with (
        open_inspection_catalog(adapter=adapter, connection=connection),
        pytest.raises(PlannerInputError, match=test_case.expected_error_fragment),
    ):
        _ = _gather_eligible_target_maxes(
            cursor_models=infos,
            results=results,
            adapter=cast(Any, adapter),
            connection=connection,
            execute=EligibleMaxExecute(
                failing_relation=test_case.failing_relation, latency_seconds=_LATENCY_SECONDS
            ),
            invocation_time=datetime(2026, 1, 20, tzinfo=UTC),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
