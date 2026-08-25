from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.planner._helpers.pruning.run_despite_unchanged import (
    build_run_despite_unchanged_planning_result,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import PlannerScope, RunDespiteUnchangedPlanningResult
from sqlbuild.compiler.source_freshness.models import DirectSourceFreshnessPlanningResult
from sqlbuild.spec.contracts.types import SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    RunDespiteUnchangedPlanningTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_run_despite_unchanged_scope,
    build_run_despite_unchanged_source_freshness,
)

_NOW: datetime = datetime(2026, 6, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        RunDespiteUnchangedPlanningTestCase(
            description="always mode marks root and downstream stale",
            run_despite_unchanged="always",
            materialized="table",
            data_version=None,
            value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
            expected_root_model_names=frozenset({"rolling_orders"}),
            expected_stale_model_names=frozenset({"rolling_orders", "orders_mart"}),
        ),
        RunDespiteUnchangedPlanningTestCase(
            description="active duration marks root and downstream stale",
            run_despite_unchanged="30d",
            materialized="table",
            data_version="2026-06-01T00:00:00+00:00",
            value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
            expected_root_model_names=frozenset({"rolling_orders"}),
            expected_stale_model_names=frozenset({"rolling_orders", "orders_mart"}),
        ),
        RunDespiteUnchangedPlanningTestCase(
            description="expired duration leaves root and downstream current",
            run_despite_unchanged="1d",
            materialized="table",
            data_version="2026-06-01T00:00:00+00:00",
            value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
            expected_root_model_names=frozenset(),
            expected_stale_model_names=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_run_despite_unchanged_config_when_planning_then_returns_expected_roots(
    test_case: RunDespiteUnchangedPlanningTestCase,
) -> None:
    scope: PlannerScope = build_run_despite_unchanged_scope(
        run_despite_unchanged=test_case.run_despite_unchanged,
        materialized=test_case.materialized,
    )
    source_freshness: DirectSourceFreshnessPlanningResult = (
        build_run_despite_unchanged_source_freshness(
            data_version=test_case.data_version,
            value_kind=test_case.value_kind,
            observed_at=_NOW,
        )
    )

    result: RunDespiteUnchangedPlanningResult = build_run_despite_unchanged_planning_result(
        scope=scope,
        source_freshness=source_freshness,
        already_stale_model_names=frozenset(),
        now=_NOW,
    )

    assert result.root_model_names == test_case.expected_root_model_names
    assert result.stale_model_names == test_case.expected_stale_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        RunDespiteUnchangedPlanningTestCase(
            description="invalid duration raises clear error",
            run_despite_unchanged="30days",
            materialized="table",
            data_version="2026-06-01T00:00:00+00:00",
            value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
            expected_root_model_names=frozenset(),
            expected_stale_model_names=frozenset(),
            expected_error_fragment="must be 'always' or a positive duration",
        ),
        RunDespiteUnchangedPlanningTestCase(
            description="non-table materialization raises clear error",
            run_despite_unchanged="always",
            materialized="view",
            data_version=None,
            value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
            expected_root_model_names=frozenset(),
            expected_stale_model_names=frozenset(),
            expected_error_fragment="only table materializations support it",
        ),
        RunDespiteUnchangedPlanningTestCase(
            description="integer freshness raises clear error for duration",
            run_despite_unchanged="30d",
            materialized="table",
            data_version="1",
            value_kind=SourceFreshnessValueKind.INTEGER.value,
            expected_root_model_names=frozenset(),
            expected_stale_model_names=frozenset(),
            expected_error_fragment="requires timestamp source freshness",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_run_despite_unchanged_config_when_planning_then_raises_error(
    test_case: RunDespiteUnchangedPlanningTestCase,
) -> None:
    scope: PlannerScope = build_run_despite_unchanged_scope(
        run_despite_unchanged=test_case.run_despite_unchanged,
        materialized=test_case.materialized,
    )
    source_freshness: DirectSourceFreshnessPlanningResult = (
        build_run_despite_unchanged_source_freshness(
            data_version=test_case.data_version,
            value_kind=test_case.value_kind,
            observed_at=_NOW,
        )
    )

    with pytest.raises(PlannerInputError) as exc_info:
        build_run_despite_unchanged_planning_result(
            scope=scope,
            source_freshness=source_freshness,
            already_stale_model_names=frozenset(),
            now=_NOW,
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in str(exc_info.value)
