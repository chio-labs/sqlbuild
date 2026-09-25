"""Janitor safety for relation names that differ only by case."""

from __future__ import annotations

import pytest

from sqlbuild.executor.janitor.constants import CASE_COLLISION_REASON
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.main.plan import build_janitor_plan
from sqlbuild.executor.janitor.models import JanitorDirectModeSettings, JanitorPlan
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorCaseSafetyTestCase,
    relation_info,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FakeJanitorAdapter,
    build_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorCaseSafetyTestCase(
            description="virtual mode never drops an excluded table through a quoted twin",
            relation_names=("orders__v0", "Orders__v0"),
            direct_mode=False,
            tracked_names=("orders__v0",),
            exclude_patterns=("orders__v0",),
            expected_skipped_relations=(
                ("analytics.orders__v0", "relation matches exclude pattern 'orders__v0'"),
                ("analytics.Orders__v0", "relation matches exclude pattern 'orders__v0'"),
            ),
            expected_dropped_targets=(),
        ),
        JanitorCaseSafetyTestCase(
            description="virtual mode skips relations whose folded names collide",
            relation_names=("orders__v0", "Orders__v0"),
            direct_mode=False,
            tracked_names=("orders__v0",),
            exclude_patterns=(),
            expected_skipped_relations=(
                ("analytics.orders__v0", CASE_COLLISION_REASON),
                ("analytics.Orders__v0", CASE_COLLISION_REASON),
            ),
            expected_dropped_targets=(),
        ),
        JanitorCaseSafetyTestCase(
            description="virtual mode still drops a non-colliding tracked relation",
            relation_names=("orders__v0",),
            direct_mode=False,
            tracked_names=("orders__v0",),
            exclude_patterns=(),
            expected_skipped_relations=(),
            expected_dropped_targets=("analytics.orders__v0",),
        ),
        JanitorCaseSafetyTestCase(
            description="virtual exclude patterns match regardless of case",
            relation_names=("orders__v0",),
            direct_mode=False,
            tracked_names=("orders__v0",),
            exclude_patterns=("ORDERS__*",),
            expected_skipped_relations=(
                ("analytics.orders__v0", "relation matches exclude pattern 'ORDERS__*'"),
            ),
            expected_dropped_targets=(),
        ),
        JanitorCaseSafetyTestCase(
            description="direct exclude patterns match regardless of case",
            relation_names=("old_orders",),
            direct_mode=True,
            tracked_names=("old_orders",),
            exclude_patterns=("ANALYTICS.OLD_*",),
            expected_skipped_relations=(
                ("analytics.old_orders", "relation matches exclude pattern 'ANALYTICS.OLD_*'"),
            ),
            expected_dropped_targets=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_case_variant_relations_when_running_janitor_then_excluded_tables_are_not_dropped(
    test_case: JanitorCaseSafetyTestCase,
) -> None:
    adapter: FakeJanitorAdapter = FakeJanitorAdapter(
        relation_infos=tuple(relation_info(name) for name in test_case.relation_names),
        tracked_relations=tuple((None, "analytics", name) for name in test_case.tracked_names),
    )

    plan: JanitorPlan = build_janitor_plan(
        project=build_project(),
        adapter=adapter,
        connection=object(),
        retention_days=0,
        exclude_patterns=test_case.exclude_patterns,
        direct_settings=JanitorDirectModeSettings(enabled=test_case.direct_mode),
    )
    execute_janitor_plan(plan=plan, adapter=adapter, connection=object())

    assert (
        tuple(
            (skipped.key.display_name(), skipped.reason)
            for skipped in filter(
                lambda skipped: skipped.key.name != "_sqlbuild_fingerprints",
                plan.skipped_relations,
            )
        )
        == test_case.expected_skipped_relations
    )
    assert tuple(adapter.dropped_targets) == test_case.expected_dropped_targets
    assert adapter.renamed_targets == []
