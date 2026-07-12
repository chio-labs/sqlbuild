from __future__ import annotations

import pytest

from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.types import LifeCycleEventKind
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.clone.helpers.operations import clone_relation
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.models import RelationLookup
from tests.unit.src.sqlbuild.executor.clone.helpers._test_types import (
    CloneRelationExecutionTestCase,
)
from tests.unit.src.sqlbuild.executor.clone.helpers.helpers import (
    FakeCloneAdapter,
    build_clone_model_entry,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneRelationExecutionTestCase(
            description="uses zero copy clone action and SQL by default when adapter supports it",
            hard_copy=False,
            supports_zero_copy_clone=True,
            expected_action=CloneAction.CLONED,
            expected_status=CloneStatus.SUCCESS,
            expected_statements=(
                "DROP TABLE IF EXISTS dev.fact_orders",
                "CREATE TABLE dev.fact_orders CLONE prod.fact_orders",
            ),
        ),
        CloneRelationExecutionTestCase(
            description="uses hard copy action and CTAS SQL when requested",
            hard_copy=True,
            supports_zero_copy_clone=True,
            expected_action=CloneAction.COPIED,
            expected_status=CloneStatus.SUCCESS,
            expected_statements=(
                "DROP TABLE IF EXISTS dev.fact_orders",
                "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        ),
        CloneRelationExecutionTestCase(
            description="uses copied action when adapter lacks zero copy clone support",
            hard_copy=False,
            supports_zero_copy_clone=False,
            expected_action=CloneAction.COPIED,
            expected_status=CloneStatus.SUCCESS,
            expected_statements=(
                "DROP TABLE IF EXISTS dev.fact_orders",
                "CREATE TABLE dev.fact_orders CLONE prod.fact_orders",
            ),
        ),
        CloneRelationExecutionTestCase(
            description="mirrors transient origin into a transient clone statement",
            hard_copy=False,
            supports_zero_copy_clone=True,
            origin_is_transient=True,
            expected_action=CloneAction.CLONED,
            expected_status=CloneStatus.SUCCESS,
            expected_statements=(
                "DROP TABLE IF EXISTS dev.fact_orders",
                "CREATE TRANSIENT TABLE dev.fact_orders CLONE prod.fact_orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_relation_when_executing_then_records_sql_and_reports_copy_mode(
    test_case: CloneRelationExecutionTestCase,
) -> None:
    adapter: FakeCloneAdapter = FakeCloneAdapter(
        supports_zero_copy=test_case.supports_zero_copy_clone,
        origin_is_transient=test_case.origin_is_transient,
    )
    origin_entry: ModelPlanEntry = build_clone_model_entry(schema="prod", name="fact_orders")
    destination_entry: ModelPlanEntry = build_clone_model_entry(schema="dev", name="fact_orders")
    origin_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=object(),
        locations=((None, "prod", "fact_orders"),),
    )

    result: CloneItemResult = clone_relation(
        destination_entry=destination_entry,
        origin_entry=origin_entry,
        adapter=adapter,
        destination_connection=object(),
        hard_copy=test_case.hard_copy,
        origin_lookup=origin_lookup,
    )

    assert result.action == test_case.expected_action
    assert result.status == test_case.expected_status
    assert result.origin_relation == "prod.fact_orders"
    assert result.destination_relation == "dev.fact_orders"
    assert result.duration_seconds is not None
    assert tuple(event.kind for event in result.executed_statements) == (
        LifeCycleEventKind.SQL,
        LifeCycleEventKind.SQL,
    )
    assert tuple(event.content for event in result.executed_statements) == (
        test_case.expected_statements
    )
    assert tuple(adapter.executed_statements) == test_case.expected_statements
