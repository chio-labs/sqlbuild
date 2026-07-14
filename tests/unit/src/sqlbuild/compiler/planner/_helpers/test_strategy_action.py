from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.planner._helpers.output.strategy import resolve_model_plan_action
from sqlbuild.compiler.planner.models import ChangeDetectionResult, SchemaFinding
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    SchemaColumnSource,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    IncrementalStrategyErrorTestCase,
    ResolveModelPlanActionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_strategy_change_result,
    build_strategy_error_change_result,
    build_strategy_error_model,
    build_strategy_model,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveModelPlanActionTestCase(
            description="view always creates regardless of change kind",
            materialized="view",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.CREATE_VIEW,
            expected_reason=PlanReason.NO_CHANGE,
        ),
        ResolveModelPlanActionTestCase(
            description="view with full refresh returns full refresh reason",
            materialized="view",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=True,
            expected_action=PlanAction.CREATE_VIEW,
            expected_reason=PlanReason.FULL_REFRESH,
        ),
        ResolveModelPlanActionTestCase(
            description="view with first run returns first run reason",
            materialized="view",
            incremental_strategy=None,
            change_kind=ChangeKind.FIRST_RUN,
            query_changed=False,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.CREATE_VIEW,
            expected_reason=PlanReason.FIRST_RUN,
        ),
        ResolveModelPlanActionTestCase(
            description="table with full refresh creates table",
            materialized="table",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=True,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.FULL_REFRESH,
        ),
        ResolveModelPlanActionTestCase(
            description="table first run creates table",
            materialized="table",
            incremental_strategy=None,
            change_kind=ChangeKind.FIRST_RUN,
            query_changed=False,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.FIRST_RUN,
        ),
        ResolveModelPlanActionTestCase(
            description="table with no change always rebuilds",
            materialized="table",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.NO_CHANGE,
        ),
        ResolveModelPlanActionTestCase(
            description="table with query change rebuilds",
            materialized="table",
            incremental_strategy=None,
            change_kind=ChangeKind.QUERY_CHANGED,
            query_changed=True,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.QUERY_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental first run creates table",
            materialized="incremental",
            incremental_strategy="delete_insert",
            change_kind=ChangeKind.FIRST_RUN,
            query_changed=False,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.FIRST_RUN,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental with full backfill from query change creates table",
            materialized="incremental",
            incremental_strategy="merge",
            change_kind=ChangeKind.QUERY_CHANGED,
            query_changed=True,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.QUERY_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental append with normal change",
            materialized="incremental",
            incremental_strategy="append",
            change_kind=ChangeKind.QUERY_CHANGED,
            query_changed=True,
            backfill_action=BackfillAction.BOUNDED,
            backfill_duration="30d",
            full_refresh=False,
            expected_action=PlanAction.INCREMENTAL_APPEND,
            expected_reason=PlanReason.QUERY_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental delete_insert with schema change",
            materialized="incremental",
            incremental_strategy="delete_insert",
            change_kind=ChangeKind.SCHEMA_CHANGED,
            query_changed=False,
            backfill_action=BackfillAction.BOUNDED,
            backfill_duration="7d",
            full_refresh=False,
            expected_action=PlanAction.INCREMENTAL_DELETE_INSERT,
            expected_reason=PlanReason.SCHEMA_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental merge with normal incremental",
            materialized="incremental",
            incremental_strategy="merge",
            change_kind=ChangeKind.SCHEMA_CHANGED,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.INCREMENTAL_MERGE,
            expected_reason=PlanReason.SCHEMA_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental append with no change always runs",
            materialized="incremental",
            incremental_strategy="append",
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.INCREMENTAL_APPEND,
            expected_reason=PlanReason.NORMAL_INCREMENTAL,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental with full refresh creates table regardless of strategy",
            materialized="incremental",
            incremental_strategy="merge",
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=True,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.FULL_REFRESH,
        ),
        ResolveModelPlanActionTestCase(
            description="table with schema change rebuilds",
            materialized="table",
            incremental_strategy=None,
            change_kind=ChangeKind.SCHEMA_CHANGED,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.SCHEMA_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="view with query change returns query changed reason",
            materialized="view",
            incremental_strategy=None,
            change_kind=ChangeKind.QUERY_CHANGED,
            query_changed=True,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.CREATE_VIEW,
            expected_reason=PlanReason.QUERY_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description="view with schema change returns schema changed reason",
            materialized="view",
            incremental_strategy=None,
            change_kind=ChangeKind.SCHEMA_CHANGED,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.CREATE_VIEW,
            expected_reason=PlanReason.SCHEMA_CHANGED,
        ),
        ResolveModelPlanActionTestCase(
            description=(
                "incremental with full backfill from schema change creates table with schema reason"
            ),
            materialized="incremental",
            incremental_strategy="append",
            change_kind=ChangeKind.SCHEMA_CHANGED,
            query_changed=False,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.CREATE_TABLE,
            expected_reason=PlanReason.SCHEMA_CHANGED,
            schema_findings=(
                SchemaFinding(
                    kind=SchemaChangeKind.COLUMN_ADDED,
                    column_name="status",
                    source=SchemaColumnSource.YML,
                    expected_type="VARCHAR",
                ),
            ),
        ),
        ResolveModelPlanActionTestCase(
            description="unknown materialized config routes to custom action",
            materialized="unknown_custom_thing",
            incremental_strategy=None,
            change_kind=ChangeKind.FIRST_RUN,
            query_changed=False,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.CUSTOM,
            expected_reason=PlanReason.FIRST_RUN,
        ),
        ResolveModelPlanActionTestCase(
            description="disabled model returns skip with disabled reason",
            materialized="table",
            incremental_strategy=None,
            change_kind=ChangeKind.FIRST_RUN,
            query_changed=False,
            backfill_action=BackfillAction.FULL,
            full_refresh=False,
            expected_action=PlanAction.SKIP,
            expected_reason=PlanReason.DISABLED,
            enabled=False,
        ),
        ResolveModelPlanActionTestCase(
            description="disabled incremental model returns skip regardless of strategy",
            materialized="incremental",
            incremental_strategy="delete_insert",
            change_kind=ChangeKind.QUERY_CHANGED,
            query_changed=True,
            backfill_action=BackfillAction.BOUNDED,
            full_refresh=False,
            expected_action=PlanAction.SKIP,
            expected_reason=PlanReason.DISABLED,
            enabled=False,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental delete_insert with no change always runs",
            materialized="incremental",
            incremental_strategy="delete_insert",
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.INCREMENTAL_DELETE_INSERT,
            expected_reason=PlanReason.NORMAL_INCREMENTAL,
        ),
        ResolveModelPlanActionTestCase(
            description="incremental merge with no change always runs",
            materialized="incremental",
            incremental_strategy="merge",
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.INCREMENTAL_MERGE,
            expected_reason=PlanReason.NORMAL_INCREMENTAL,
        ),
        ResolveModelPlanActionTestCase(
            description="snapshot with no change returns snapshot action",
            materialized="snapshot",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=False,
            expected_action=PlanAction.SNAPSHOT,
            expected_reason=PlanReason.NORMAL_INCREMENTAL,
        ),
        ResolveModelPlanActionTestCase(
            description="snapshot with full refresh keeps snapshot action and full refresh reason",
            materialized="snapshot",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            query_changed=False,
            backfill_action=BackfillAction.FORWARD_ONLY,
            full_refresh=True,
            expected_action=PlanAction.SNAPSHOT,
            expected_reason=PlanReason.FULL_REFRESH,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_and_changes_when_resolving_action_then_returns_expected(
    test_case: ResolveModelPlanActionTestCase,
) -> None:
    model: CompiledModel = build_strategy_model(test_case)
    change_result: ChangeDetectionResult = build_strategy_change_result(test_case)

    action: PlanAction
    reason: PlanReason
    action, reason = resolve_model_plan_action(
        model=model,
        change_result=change_result,
        full_refresh=test_case.full_refresh,
    )

    assert action == test_case.expected_action
    assert reason == test_case.expected_reason


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalStrategyErrorTestCase(
            description="incremental without strategy raises",
            materialized="incremental",
            incremental_strategy=None,
            change_kind=ChangeKind.NO_CHANGE,
            expected_error_type=ValueError,
            expected_error_fragment="missing required incremental_strategy",
        ),
        IncrementalStrategyErrorTestCase(
            description="incremental with unknown strategy raises",
            materialized="incremental",
            incremental_strategy="upsert",
            change_kind=ChangeKind.QUERY_CHANGED,
            expected_error_type=ValueError,
            expected_error_fragment="unknown strategy 'upsert'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_with_bad_strategy_when_resolving_action_then_raises(
    test_case: IncrementalStrategyErrorTestCase,
) -> None:
    model: CompiledModel = build_strategy_error_model(test_case)
    change_result: ChangeDetectionResult = build_strategy_error_change_result(test_case)

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        resolve_model_plan_action(
            model=model,
            change_result=change_result,
            full_refresh=False,
        )
