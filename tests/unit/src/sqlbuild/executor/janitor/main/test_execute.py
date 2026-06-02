"""Tests for janitor plan execution."""

from __future__ import annotations

import pytest

from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.models import (
    JanitorDeleteCandidate,
    JanitorDetachedVirtualEnvironmentCandidate,
    JanitorPlan,
    JanitorRelationKey,
)
from tests.unit.src.sqlbuild.executor.janitor.main._test_types import (
    JanitorExecutionOrderTestCase,
)
from tests.unit.src.sqlbuild.executor.janitor.main.helpers import (
    FailingDropAdapter,
    relation_info_for_test,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorExecutionOrderTestCase(
            description="state cleanup is skipped when physical deletion fails",
            expected_error_fragment="drop failed",
            expected_deleted_state_items=(),
        )
    ],
    ids=["state cleanup is skipped when physical deletion fails"],
)
def test_given_physical_drop_failure_when_executing_janitor_then_state_cleanup_is_skipped(
    test_case: JanitorExecutionOrderTestCase,
) -> None:
    deleted_state_items: list[str] = []
    adapter: FailingDropAdapter = FailingDropAdapter(message=test_case.expected_error_fragment)

    with pytest.raises(RuntimeError) as exc_info:
        execute_janitor_plan(
            plan=JanitorPlan(
                target_name="dev",
                retention_days=0,
                candidates=(
                    JanitorDeleteCandidate(
                        key=JanitorRelationKey(
                            database=None,
                            schema="dev__sqb_physical",
                            name="orders__v_old",
                        ),
                        relation=relation_info_for_test(
                            schema="dev__sqb_physical",
                            name="orders__v_old",
                        ),
                        age_timestamp=None,
                    ),
                ),
                detached_virtual_environment_candidates=(
                    JanitorDetachedVirtualEnvironmentCandidate(
                        virtual_target_name="dev",
                        updated_at=None,
                    ),
                ),
            ),
            adapter=adapter,
            connection=object(),
            delete_detached_virtual_environment=lambda candidate: deleted_state_items.append(
                candidate.virtual_target_name
            ),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert tuple(deleted_state_items) == test_case.expected_deleted_state_items
    assert adapter.dropped_targets == ["dev__sqb_physical.orders__v_old"]
