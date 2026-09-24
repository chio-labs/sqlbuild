"""Janitor planning against adapters that read relation ages separately from listing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import JanitorDirectModeSettings, JanitorPlan
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
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
