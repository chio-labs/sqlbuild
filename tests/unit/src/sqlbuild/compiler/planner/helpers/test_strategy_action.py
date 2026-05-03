from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.planner.helpers.strategy import resolve_model_plan_action
from sqlbuild.compiler.planner.models import ChangeDetectionResult, SchemaFinding
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    SchemaColumnSource,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    ResolveModelPlanActionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_strategy_change_result,
    build_strategy_model,
)

RESOLVE_ACTION_TEST_CASES: list[ResolveModelPlanActionTestCase] = [
    ResolveModelPlanActionTestCase(
        description="view always creates regardless of change kind",
        materialized="view",
        incremental_strategy=None,
        change_kind=ChangeKind.NO_CHANGE,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
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
        backfill_action=BackfillAction.WARN_ONLY,
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
        backfill_action=BackfillAction.WARN_ONLY,
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
        description="table with no change skips",
        materialized="table",
        incremental_strategy=None,
        change_kind=ChangeKind.NO_CHANGE,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        full_refresh=False,
        expected_action=PlanAction.SKIP,
        expected_reason=PlanReason.NO_CHANGE,
    ),
    ResolveModelPlanActionTestCase(
        description="table with query change rebuilds",
        materialized="table",
        incremental_strategy=None,
        change_kind=ChangeKind.QUERY_CHANGED,
        query_changed=True,
        backfill_action=BackfillAction.WARN_ONLY,
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
        backfill_action=BackfillAction.WARN_ONLY,
        full_refresh=False,
        expected_action=PlanAction.INCREMENTAL_MERGE,
        expected_reason=PlanReason.SCHEMA_CHANGED,
    ),
    ResolveModelPlanActionTestCase(
        description="incremental with no change skips",
        materialized="incremental",
        incremental_strategy="append",
        change_kind=ChangeKind.NO_CHANGE,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
        full_refresh=False,
        expected_action=PlanAction.SKIP,
        expected_reason=PlanReason.NO_CHANGE,
    ),
    ResolveModelPlanActionTestCase(
        description="incremental with full refresh creates table regardless of strategy",
        materialized="incremental",
        incremental_strategy="merge",
        change_kind=ChangeKind.NO_CHANGE,
        query_changed=False,
        backfill_action=BackfillAction.WARN_ONLY,
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
        backfill_action=BackfillAction.WARN_ONLY,
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
        backfill_action=BackfillAction.WARN_ONLY,
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
        backfill_action=BackfillAction.WARN_ONLY,
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
        description="missing materialized config defaults to table behavior",
        materialized="unknown_custom_thing",
        incremental_strategy=None,
        change_kind=ChangeKind.FIRST_RUN,
        query_changed=False,
        backfill_action=BackfillAction.FULL,
        full_refresh=False,
        expected_action=PlanAction.CREATE_TABLE,
        expected_reason=PlanReason.FIRST_RUN,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_ACTION_TEST_CASES,
    ids=[case.description for case in RESOLVE_ACTION_TEST_CASES],
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
