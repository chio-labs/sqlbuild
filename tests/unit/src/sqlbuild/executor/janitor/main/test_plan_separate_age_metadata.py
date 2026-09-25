"""Janitor planning against adapters that read relation ages separately from listing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorDirectModeSettings,
    JanitorPlan,
    JanitorRelationScope,
)
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorAgeReadScopeTestCase,
    JanitorSeparateAgeMetadataPlanTestCase,
    relation_info,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    SeparateAgeMetadataJanitorAdapter,
    build_project,
)

OLD_TIME: datetime = datetime.now(UTC) - timedelta(days=30)
RECENT_TIME: datetime = datetime.now(UTC) - timedelta(days=1)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorSeparateAgeMetadataPlanTestCase(
            description="separately read ages decide which stale relations are old enough",
            relation_ages={"old_orders": OLD_TIME, "recent_orders": RECENT_TIME},
            expected_candidate_names=("old_orders",),
            expected_skipped_relations=(
                ("analytics.recent_orders", "relation is newer than 7 days"),
            ),
        ),
        JanitorSeparateAgeMetadataPlanTestCase(
            description="relations without separately read ages are skipped as unknown",
            relation_ages={},
            expected_candidate_names=(),
            expected_skipped_relations=(
                ("analytics.old_orders", "relation age is unavailable"),
                ("analytics.recent_orders", "relation age is unavailable"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_reading_ages_separately_when_planning_janitor_then_uses_those_ages(
    test_case: JanitorSeparateAgeMetadataPlanTestCase,
) -> None:
    adapter: SeparateAgeMetadataJanitorAdapter = SeparateAgeMetadataJanitorAdapter(
        relation_infos=(relation_info("old_orders"), relation_info("recent_orders")),
        relation_ages=test_case.relation_ages,
    )

    plan: JanitorPlan = build_janitor_plan(
        project=build_project(),
        adapter=adapter,
        connection=object(),
        retention_days=7,
        delete_tracked_only=False,
        direct_settings=JanitorDirectModeSettings(enabled=True),
    )

    assert (
        tuple(candidate.key.name for candidate in plan.candidates)
        == test_case.expected_candidate_names
    )
    assert (
        tuple((skipped.key.display_name(), skipped.reason) for skipped in plan.skipped_relations)
        == test_case.expected_skipped_relations
    )
    assert len(adapter.age_metadata_requests) == 1


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorAgeReadScopeTestCase(
            description="direct mode reads ages only for unfiltered stale relations",
            relation_infos=(
                relation_info("orders"),
                relation_info("old_orders"),
                relation_info("stray_orders"),
                relation_info("tmp_orders"),
                relation_info("_sqlbuild_fingerprints"),
                relation_info("Mixed_Orders"),
            ),
            direct_mode=True,
            delete_tracked_only=True,
            tracked_relations=(
                (None, "analytics", "old_orders"),
                (None, "analytics", "tmp_orders"),
                (None, "analytics", "Mixed_Orders"),
            ),
            exclude_patterns=("tmp_*",),
            protected_relation_keys=frozenset(),
            expected_age_requests=(("old_orders",),),
        ),
        JanitorAgeReadScopeTestCase(
            description="no age read happens when nothing survives the filters",
            relation_infos=(relation_info("orders"), relation_info("stray_orders")),
            direct_mode=True,
            delete_tracked_only=True,
            tracked_relations=(),
            exclude_patterns=(),
            protected_relation_keys=frozenset(),
            expected_age_requests=(),
        ),
        JanitorAgeReadScopeTestCase(
            description="zero retention does not read ages",
            relation_infos=(relation_info("orders"), relation_info("old_orders")),
            direct_mode=True,
            delete_tracked_only=False,
            tracked_relations=(),
            exclude_patterns=(),
            protected_relation_keys=frozenset(),
            expected_age_requests=(),
            retention_days=0,
        ),
        JanitorAgeReadScopeTestCase(
            description="zero retention in virtual mode does not read ages",
            relation_infos=(relation_info("orders"), relation_info("orders__v0")),
            direct_mode=False,
            delete_tracked_only=False,
            tracked_relations=(),
            exclude_patterns=(),
            protected_relation_keys=frozenset(),
            expected_age_requests=(),
            retention_days=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_filtered_relations_when_planning_janitor_then_ages_are_read_for_candidates_only(
    test_case: JanitorAgeReadScopeTestCase,
) -> None:
    adapter: SeparateAgeMetadataJanitorAdapter = SeparateAgeMetadataJanitorAdapter(
        relation_infos=test_case.relation_infos,
        relation_ages={},
        tracked_relations=test_case.tracked_relations,
    )

    build_janitor_plan(
        project=build_project(),
        adapter=adapter,
        connection=object(),
        retention_days=test_case.retention_days,
        delete_tracked_only=test_case.delete_tracked_only,
        exclude_patterns=test_case.exclude_patterns,
        relation_scope=JanitorRelationScope(
            protected_relation_keys=test_case.protected_relation_keys
        ),
        direct_settings=JanitorDirectModeSettings(enabled=test_case.direct_mode),
    )

    assert tuple(adapter.age_metadata_requests) == test_case.expected_age_requests
