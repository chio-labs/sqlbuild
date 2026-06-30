from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.local_node_planning import classify_local_node_plan
from sqlbuild.shared.models import LocalNodePlanInput, LocalNodePlanOutcome
from sqlbuild.shared.types import LocalNodePlanAction, LocalNodePlanReason
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    LocalNodePlanningTestCase,
)

LOCAL_NODE_PLANNING_TEST_CASES: list[LocalNodePlanningTestCase] = [
    LocalNodePlanningTestCase(
        description="full refresh takes precedence over all local state",
        fingerprint_exists=False,
        relation_exists=False,
        full_refresh=True,
        local_hash="current",
        previous_hash="previous",
        expected_action=LocalNodePlanAction.RUN,
        expected_reason=LocalNodePlanReason.FULL_REFRESH,
    ),
    LocalNodePlanningTestCase(
        description="missing fingerprint is first run",
        fingerprint_exists=False,
        relation_exists=True,
        full_refresh=False,
        local_hash="current",
        previous_hash=None,
        expected_action=LocalNodePlanAction.RUN,
        expected_reason=LocalNodePlanReason.FIRST_RUN,
    ),
    LocalNodePlanningTestCase(
        description="missing relation with fingerprint reruns relation",
        fingerprint_exists=True,
        relation_exists=False,
        full_refresh=False,
        local_hash="current",
        previous_hash="current",
        expected_action=LocalNodePlanAction.RUN,
        expected_reason=LocalNodePlanReason.RELATION_MISSING,
    ),
    LocalNodePlanningTestCase(
        description="changed local hash reruns relation",
        fingerprint_exists=True,
        relation_exists=True,
        full_refresh=False,
        local_hash="current",
        previous_hash="previous",
        expected_action=LocalNodePlanAction.RUN,
        expected_reason=LocalNodePlanReason.LOCAL_CHANGED,
    ),
    LocalNodePlanningTestCase(
        description="matching local hash is current",
        fingerprint_exists=True,
        relation_exists=True,
        full_refresh=False,
        local_hash="current",
        previous_hash="current",
        expected_action=LocalNodePlanAction.CURRENT,
        expected_reason=LocalNodePlanReason.NO_CHANGE,
    ),
    LocalNodePlanningTestCase(
        description="missing local hash skips hash comparison",
        fingerprint_exists=True,
        relation_exists=True,
        full_refresh=False,
        local_hash=None,
        previous_hash="previous",
        expected_action=LocalNodePlanAction.CURRENT,
        expected_reason=LocalNodePlanReason.NO_CHANGE,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    LOCAL_NODE_PLANNING_TEST_CASES,
    ids=[case.description for case in LOCAL_NODE_PLANNING_TEST_CASES],
)
def test_given_local_node_state_when_classifying_then_returns_expected_outcome(
    test_case: LocalNodePlanningTestCase,
) -> None:
    outcome: LocalNodePlanOutcome = classify_local_node_plan(
        LocalNodePlanInput(
            fingerprint_exists=test_case.fingerprint_exists,
            relation_exists=test_case.relation_exists,
            full_refresh=test_case.full_refresh,
            local_hash=test_case.local_hash,
            previous_hash=test_case.previous_hash,
        )
    )

    assert outcome.action == test_case.expected_action
    assert outcome.reason == test_case.expected_reason
