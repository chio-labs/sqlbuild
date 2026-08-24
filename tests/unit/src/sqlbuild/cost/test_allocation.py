from __future__ import annotations

from decimal import Decimal

import pytest

from sqlbuild.cost._helpers.allocation import allocate_run_cost
from sqlbuild.cost.models import QueryCostObservation, RunCostSummary
from sqlbuild.cost.types import CostStatus
from tests.unit.src.sqlbuild.cost._test_types import AllocationTestCase
from tests.unit.src.sqlbuild.cost.helpers import build_query_cost_observation


@pytest.mark.parametrize(
    "test_case",
    [
        AllocationTestCase(
            description="visible concurrent query shares busy time",
            expected_status=CostStatus.COMPLETE,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_visible_concurrent_query_when_allocating_then_busy_time_is_shared(
    test_case: AllocationTestCase,
) -> None:
    observations: tuple[QueryCostObservation, ...] = (
        build_query_cost_observation(
            query_id="run-query",
            start_seconds=0,
            end_seconds=10,
            run_id="run-1",
            resource_type="model",
            resource_name="orders",
        ),
        build_query_cost_observation(
            query_id="other-query",
            start_seconds=5,
            end_seconds=15,
            run_id=None,
            resource_type=None,
            resource_name=None,
        ),
    )

    summary: RunCostSummary = allocate_run_cost(
        observations=observations,
        run_id="run-1",
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == 1
    assert summary.attributed_seconds == Decimal("7.5")
    assert summary.estimated_compute_credits == Decimal("7.5") / Decimal(3600)
    assert summary.estimated_usd == summary.estimated_compute_credits * Decimal("3.00")


@pytest.mark.parametrize(
    "test_case",
    [
        AllocationTestCase(
            description="concurrent run queries do not double count compute",
            expected_status=CostStatus.COMPLETE,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_concurrent_run_queries_when_allocating_then_compute_is_not_double_counted(
    test_case: AllocationTestCase,
) -> None:
    observations: tuple[QueryCostObservation, ...] = (
        build_query_cost_observation(
            query_id="query-1",
            start_seconds=0,
            end_seconds=10,
            run_id="run-1",
            resource_type="model",
            resource_name="orders",
        ),
        build_query_cost_observation(
            query_id="query-2",
            start_seconds=0,
            end_seconds=10,
            run_id="run-1",
            resource_type="model",
            resource_name="customers",
        ),
    )

    summary: RunCostSummary = allocate_run_cost(
        observations=observations,
        run_id="run-1",
        usd_per_credit=Decimal("3.00"),
        rate_source="configured",
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == 2
    assert summary.attributed_seconds == Decimal("10")
    assert tuple(resource.resource_name for resource in summary.resources) == (
        "customers",
        "orders",
    )


@pytest.mark.parametrize(
    "test_case",
    [
        AllocationTestCase(
            description="unknown warehouse size produces partial summary",
            expected_status=CostStatus.PARTIAL,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_warehouse_size_when_allocating_then_summary_is_partial(
    test_case: AllocationTestCase,
) -> None:
    observations: tuple[QueryCostObservation, ...] = (
        build_query_cost_observation(
            query_id="query-1",
            start_seconds=0,
            end_seconds=10,
            run_id="run-1",
            resource_type="model",
            resource_name="orders",
            warehouse_size="Future-Large",
        ),
    )

    summary: RunCostSummary = allocate_run_cost(
        observations=observations,
        run_id="run-1",
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
    )

    assert summary.status == test_case.expected_status
    assert summary.query_count == 1
    assert summary.resources == ()
    assert summary.limitations == ("Unknown Snowflake warehouse size: Future-Large",)


@pytest.mark.parametrize(
    "test_case",
    [
        AllocationTestCase(
            description="no run queries produces pending summary",
            expected_status=CostStatus.PENDING,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_run_queries_when_allocating_then_summary_is_pending(
    test_case: AllocationTestCase,
) -> None:
    summary: RunCostSummary = allocate_run_cost(
        observations=(),
        run_id="run-1",
        usd_per_credit=Decimal("3.00"),
        rate_source="default",
    )

    assert summary.status == test_case.expected_status
    assert summary.message == "Snowflake query history is not complete yet."


@pytest.mark.parametrize(
    "test_case",
    [
        AllocationTestCase(
            description="mixed warehouse sizes use independent Snowflake credit rates",
            expected_status=CostStatus.COMPLETE,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mixed_warehouse_sizes_when_allocating_then_each_size_uses_its_rate(
    test_case: AllocationTestCase,
) -> None:
    observations: tuple[QueryCostObservation, ...] = (
        build_query_cost_observation(
            query_id="query-xs",
            start_seconds=0,
            end_seconds=3600,
            run_id="run-1",
            resource_type="model",
            resource_name="small_model",
            warehouse_size="X-Small",
        ),
        build_query_cost_observation(
            query_id="query-small",
            start_seconds=0,
            end_seconds=3600,
            run_id="run-1",
            resource_type="model",
            resource_name="larger_model",
            warehouse_size="Small",
        ),
    )

    summary: RunCostSummary = allocate_run_cost(
        observations=observations,
        run_id="run-1",
        usd_per_credit=Decimal("3.00"),
        rate_source="configured",
    )

    credits_by_model: dict[str, Decimal] = {
        resource.resource_name: resource.estimated_compute_credits for resource in summary.resources
    }
    assert summary.status == test_case.expected_status
    assert credits_by_model == {
        "small_model": Decimal(1),
        "larger_model": Decimal(2),
    }
    assert summary.estimated_compute_credits == Decimal(3)
