from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import JanitorExecutionResult, JanitorPlan
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorExecuteTestCase,
    JanitorPlanTestCase,
    relation_info,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FakeJanitorAdapter,
    build_project,
)

OLD_TIME: datetime = datetime.now(UTC) - timedelta(days=30)
NEW_TIME: datetime = datetime.now(UTC) - timedelta(days=1)

PLAN_TEST_CASES: list[JanitorPlanTestCase] = [
    JanitorPlanTestCase(
        description="extra old relation is eligible",
        relation_infos=(
            relation_info("orders", created_at=OLD_TIME),
            relation_info("old_orders", created_at=OLD_TIME),
        ),
        expected_candidate_names=("old_orders",),
    ),
    JanitorPlanTestCase(
        description="desired model and seed are retained",
        relation_infos=(
            relation_info("orders", created_at=OLD_TIME),
            relation_info("countries", created_at=OLD_TIME),
        ),
        expected_candidate_names=(),
    ),
    JanitorPlanTestCase(
        description="schema with active source is skipped",
        relation_infos=(relation_info("old_orders", created_at=OLD_TIME),),
        source_schema="analytics",
        expected_candidate_names=(),
        expected_skipped_schema_sources=("raw_orders",),
    ),
    JanitorPlanTestCase(
        description="new relation is skipped by retention",
        relation_infos=(relation_info("old_orders", created_at=NEW_TIME),),
        expected_candidate_names=(),
        expected_skipped_relation_reasons=("relation is newer than 7 days",),
    ),
    JanitorPlanTestCase(
        description="unknown age skipped when retention is enabled",
        relation_infos=(relation_info("old_orders"),),
        expected_candidate_names=(),
        expected_skipped_relation_reasons=("relation age is unavailable",),
    ),
    JanitorPlanTestCase(
        description="adapter without age metadata skips when retention is enabled",
        relation_infos=(relation_info("old_orders"),),
        supports_age_metadata=False,
        expected_candidate_names=(),
        expected_skipped_relation_reasons=("adapter does not expose relation age metadata",),
    ),
    JanitorPlanTestCase(
        description="retention zero allows unknown age",
        relation_infos=(relation_info("old_orders"),),
        retention_days=0,
        supports_age_metadata=False,
        expected_candidate_names=("old_orders",),
    ),
    JanitorPlanTestCase(
        description="fingerprint table is excluded by default",
        relation_infos=(relation_info("_sqlbuild_fingerprints", created_at=OLD_TIME),),
        expected_candidate_names=(),
        expected_skipped_relation_reasons=(
            "relation matches exclude pattern '_sqlbuild_fingerprints'",
        ),
    ),
    JanitorPlanTestCase(
        description="configured exclude pattern skips matching relation",
        relation_infos=(relation_info("partition_state", created_at=OLD_TIME),),
        exclude_patterns=("partition_*",),
        expected_candidate_names=(),
        expected_skipped_relation_reasons=("relation matches exclude pattern 'partition_*'",),
    ),
    JanitorPlanTestCase(
        description="untracked relation is skipped when tracked-only is enabled",
        relation_infos=(relation_info("old_orders", created_at=OLD_TIME),),
        delete_tracked_only=True,
        expected_candidate_names=(),
        expected_skipped_relation_reasons=("relation is not tracked by SQLBuild",),
    ),
    JanitorPlanTestCase(
        description="tracked relation is eligible when tracked-only is enabled",
        relation_infos=(relation_info("old_orders", created_at=OLD_TIME),),
        delete_tracked_only=True,
        tracked_relations=((None, "analytics", "old_orders"),),
        expected_candidate_names=("old_orders",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_TEST_CASES,
    ids=[case.description for case in PLAN_TEST_CASES],
)
def test_given_project_and_warehouse_when_building_janitor_plan_then_returns_expected_candidates(
    test_case: JanitorPlanTestCase,
) -> None:
    adapter: FakeJanitorAdapter = FakeJanitorAdapter(
        relation_infos=test_case.relation_infos,
        supports_age_metadata=test_case.supports_age_metadata,
        tracked_relations=test_case.tracked_relations,
    )

    plan: JanitorPlan = build_janitor_plan(
        project=build_project(source_schema=test_case.source_schema),
        adapter=adapter,
        connection=object(),
        retention_days=test_case.retention_days,
        delete_tracked_only=test_case.delete_tracked_only,
        exclude_patterns=test_case.exclude_patterns,
    )

    assert tuple(candidate.key.name for candidate in plan.candidates) == (
        test_case.expected_candidate_names
    )
    assert tuple(skipped.reason for skipped in plan.skipped_relations) == (
        test_case.expected_skipped_relation_reasons
    )
    assert (
        tuple(
            source_name
            for skipped_schema in plan.skipped_schemas
            for source_name in skipped_schema.source_names
        )
        == test_case.expected_skipped_schema_sources
    )


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorExecuteTestCase(
            description="drops all eligible candidates",
            relation_infos=(relation_info("old_orders", created_at=OLD_TIME),),
            expected_dropped_targets=("analytics.old_orders",),
        )
    ],
    ids=["drops all eligible candidates"],
)
def test_given_janitor_plan_when_executing_then_drops_expected_relations(
    test_case: JanitorExecuteTestCase,
) -> None:
    adapter: FakeJanitorAdapter = FakeJanitorAdapter(relation_infos=test_case.relation_infos)
    plan: JanitorPlan = build_janitor_plan(
        project=build_project(),
        adapter=adapter,
        connection=object(),
        retention_days=7,
        delete_tracked_only=False,
    )

    result: JanitorExecutionResult = execute_janitor_plan(
        plan=plan,
        adapter=adapter,
        connection=object(),
    )

    assert tuple(adapter.dropped_targets) == test_case.expected_dropped_targets
    assert tuple(candidate.key.name for candidate in result.deleted) == ("old_orders",)
