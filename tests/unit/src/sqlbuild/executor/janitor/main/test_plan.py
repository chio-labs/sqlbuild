from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorExecutionResult,
    JanitorPlan,
    JanitorRelationKey,
    JanitorRelationScope,
    JanitorStateCandidates,
    JanitorVirtualStatePruneCandidate,
)
from sqlbuild.virtual.state.constants import PYTHON_NODE_VERSION_TABLE
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


@pytest.mark.parametrize(
    "test_case",
    [
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
            expected_direct_state_table_names=(FINGERPRINT_TABLE_NAME,),
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
            expected_direct_state_table_names=(FINGERPRINT_TABLE_NAME,),
            expected_skipped_relation_reasons=(
                "relation matches exclude pattern '_sqlbuild_fingerprints'",
            ),
        ),
        JanitorPlanTestCase(
            description="scenario artifact is eligible when tracked-only is enabled",
            relation_infos=(
                relation_info("__sqb_a13f09c2e7b8__model__daily_revenue", created_at=OLD_TIME),
            ),
            delete_tracked_only=True,
            expected_candidate_names=("__sqb_a13f09c2e7b8__model__daily_revenue",),
        ),
        JanitorPlanTestCase(
            description="dbt scenario artifact is eligible when tracked-only is enabled",
            relation_infos=(
                relation_info("__sqb_a13f09c2e7b8__dbt_ref__stripe__payments", created_at=OLD_TIME),
            ),
            delete_tracked_only=True,
            expected_candidate_names=("__sqb_a13f09c2e7b8__dbt_ref__stripe__payments",),
        ),
        JanitorPlanTestCase(
            description="scenario-like relation is not eligible when tracked-only is enabled",
            relation_infos=(
                relation_info("__sqb_a13f09c2e7b__model__daily_revenue", created_at=OLD_TIME),
            ),
            delete_tracked_only=True,
            expected_candidate_names=(),
            expected_skipped_relation_reasons=("relation is not tracked by SQLBuild",),
        ),
        JanitorPlanTestCase(
            description="checkpoint protected relation is skipped",
            relation_infos=(
                relation_info(
                    "orders__v_old", schema="analytics__sqb_physical", created_at=OLD_TIME
                ),
            ),
            protected_relation_keys=frozenset(
                (
                    JanitorRelationKey(
                        database=None,
                        schema="analytics__sqb_physical",
                        name="orders__v_old",
                    ),
                )
            ),
            expected_candidate_names=(),
            expected_skipped_relation_reasons=(
                "relation is referenced by a retained virtual checkpoint",
            ),
        ),
        JanitorPlanTestCase(
            description="existing direct state tables are eligible for history pruning",
            relation_infos=(
                relation_info(FINGERPRINT_TABLE_NAME, created_at=OLD_TIME),
                relation_info(SOURCE_FRESHNESS_TABLE_NAME, created_at=OLD_TIME),
            ),
            direct_state_history_versions=5,
            expected_candidate_names=(),
            expected_direct_state_table_names=(
                FINGERPRINT_TABLE_NAME,
                SOURCE_FRESHNESS_TABLE_NAME,
            ),
            expected_skipped_relation_reasons=(
                "relation matches exclude pattern '_sqlbuild_fingerprints'",
                "relation matches exclude pattern '_sqlbuild_source_freshness'",
            ),
        ),
        JanitorPlanTestCase(
            description="direct state pruning is disabled when history versions is zero",
            relation_infos=(relation_info(FINGERPRINT_TABLE_NAME, created_at=OLD_TIME),),
            direct_state_history_versions=0,
            expected_candidate_names=(),
            expected_direct_state_table_names=(),
            expected_skipped_relation_reasons=(
                "relation matches exclude pattern '_sqlbuild_fingerprints'",
            ),
        ),
        JanitorPlanTestCase(
            description="virtual state pruning candidates are preserved",
            relation_infos=(),
            expected_virtual_state_table_names=(PYTHON_NODE_VERSION_TABLE,),
        ),
    ],
    ids=lambda case: case.description,
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
        relation_scope=JanitorRelationScope(
            protected_relation_keys=test_case.protected_relation_keys,
        ),
        state_candidates=JanitorStateCandidates(
            virtual_state_prune_candidates=(
                JanitorVirtualStatePruneCandidate(
                    schema="sqlbuild_state",
                    table_name=PYTHON_NODE_VERSION_TABLE,
                    reason="1 unreferenced Python identity version(s)",
                ),
            )
            if test_case.expected_virtual_state_table_names
            else (),
        ),
        direct_state_history_versions=test_case.direct_state_history_versions,
    )

    assert tuple(candidate.key.name for candidate in plan.candidates) == (
        test_case.expected_candidate_names
    )
    assert tuple(skipped.reason for skipped in plan.skipped_relations) == (
        test_case.expected_skipped_relation_reasons
    )
    assert tuple(candidate.table_name for candidate in plan.direct_state_prune_candidates) == (
        test_case.expected_direct_state_table_names
    )
    assert tuple(candidate.table_name for candidate in plan.virtual_state_prune_candidates) == (
        test_case.expected_virtual_state_table_names
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
        ),
        JanitorExecuteTestCase(
            description="prunes direct state history tables",
            relation_infos=(relation_info(FINGERPRINT_TABLE_NAME, created_at=OLD_TIME),),
            expected_dropped_targets=(),
            expected_pruned_table_names=(FINGERPRINT_TABLE_NAME,),
        ),
        JanitorExecuteTestCase(
            description="prunes virtual state orphan tables",
            relation_infos=(),
            expected_dropped_targets=(),
            expected_pruned_virtual_table_names=(PYTHON_NODE_VERSION_TABLE,),
        ),
    ],
    ids=lambda case: case.description,
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
        state_candidates=JanitorStateCandidates(
            virtual_state_prune_candidates=(
                JanitorVirtualStatePruneCandidate(
                    schema="sqlbuild_state",
                    table_name=PYTHON_NODE_VERSION_TABLE,
                    reason="1 unreferenced Python identity version(s)",
                ),
            )
            if test_case.expected_pruned_virtual_table_names
            else (),
        ),
    )
    pruned_virtual_table_names: list[str] = []

    result: JanitorExecutionResult = execute_janitor_plan(
        plan=plan,
        adapter=adapter,
        connection=object(),
        prune_virtual_state=lambda candidate: pruned_virtual_table_names.append(
            candidate.table_name
        ),
    )

    assert tuple(adapter.dropped_targets) == test_case.expected_dropped_targets
    assert tuple(candidate.key.name for candidate in result.deleted) == tuple(
        target.rsplit(".", maxsplit=1)[-1] for target in test_case.expected_dropped_targets
    )
    assert tuple(candidate.table_name for candidate in result.pruned_direct_state) == (
        test_case.expected_pruned_table_names
    )
    assert tuple(candidate.table_name for candidate in result.pruned_virtual_state) == (
        test_case.expected_pruned_virtual_table_names
    )
    assert tuple(pruned_virtual_table_names) == test_case.expected_pruned_virtual_table_names
