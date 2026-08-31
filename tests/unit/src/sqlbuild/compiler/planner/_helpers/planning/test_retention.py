from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.adapter.contract.models import (
    RelationInfo,
    RenderedRetentionChange,
    RetentionState,
)
from sqlbuild.adapter.contract.types import (
    BuiltinAdapter,
    RetentionChangePhase,
    RetentionScope,
)
from sqlbuild.compiler.planner._helpers.planning.retention import plan_retention
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    PlannerRuntime,
    PlannerScope,
    PlannerWarehouseState,
    RetentionPlanEntry,
)
from sqlbuild.compiler.planner.types import RetentionDirection, RetentionPlanPhase
from tests.unit.src.sqlbuild.compiler.planner._helpers.planning._test_types import (
    PermanentRetentionPlanningTestCase,
    RetentionPlanningErrorTestCase,
    RetentionPlanningTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.planning.helpers import (
    build_retention_planner_inputs,
)

_EXISTING_ORDERS: dict[str, RelationInfo] = {
    "orders": RelationInfo(
        database="warehouse",
        schema="analytics",
        name="orders",
        relation_type="table",
    )
}


@pytest.mark.parametrize(
    "test_case",
    [
        RetentionPlanningTestCase(
            description="matching relation remains metadata-only",
            desired_days=7,
            observed_state=RetentionState(
                request_id="orders",
                scope=RetentionScope.RELATION,
                configured_days=7,
                effective_days=7,
            ),
            expected_direction=RetentionDirection.MATCH,
            expected_phase=RetentionPlanPhase.NONE,
        ),
        RetentionPlanningTestCase(
            description="increase is planned before writes",
            desired_days=7,
            observed_state=RetentionState(
                request_id="orders",
                scope=RetentionScope.RELATION,
                configured_days=1,
                effective_days=1,
            ),
            expected_direction=RetentionDirection.INCREASE,
            expected_phase=RetentionPlanPhase.PRE,
        ),
        RetentionPlanningTestCase(
            description="decrease is planned after success",
            desired_days=1,
            observed_state=RetentionState(
                request_id="orders",
                scope=RetentionScope.RELATION,
                configured_days=7,
                effective_days=7,
            ),
            expected_direction=RetentionDirection.DECREASE,
            expected_phase=RetentionPlanPhase.POST,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_retention_policy_when_planning_then_orders_metadata_safely(
    test_case: RetentionPlanningTestCase,
) -> None:
    adapter: Mock = Mock(adapter_name=BuiltinAdapter.SNOWFLAKE.value)
    adapter.inspect_retention.return_value = test_case.observed_state
    rendered_phase: RetentionChangePhase = {
        RetentionPlanPhase.NONE: RetentionChangePhase.ALTER,
        RetentionPlanPhase.PRE: RetentionChangePhase.PREPARE,
        RetentionPlanPhase.POST: RetentionChangePhase.FINALIZE,
    }[test_case.expected_phase]
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(phase=rendered_phase, statements=("ALTER RETENTION",)),
    )
    runtime: PlannerRuntime
    warehouse: PlannerWarehouseState
    scope: PlannerScope
    runtime, warehouse, scope = build_retention_planner_inputs(
        adapter=adapter,
        desired_days=test_case.desired_days,
        existing_relations=_EXISTING_ORDERS,
        config_values={},
    )

    entries: tuple[RetentionPlanEntry, ...] = plan_retention(
        runtime=runtime,
        warehouse=warehouse,
        scope=scope,
    )

    assert len(entries) == 1
    assert entries[0].direction == test_case.expected_direction
    assert entries[0].phase == test_case.expected_phase
    assert bool(entries[0].statements) is (test_case.expected_phase != RetentionPlanPhase.NONE)


@pytest.mark.parametrize(
    "test_case",
    [
        RetentionPlanningErrorTestCase(
            description="missing Snowflake relation above transient limit",
            desired_days=30,
            expected_error_fragment="new Snowflake tables are transient",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_snowflake_relation_above_transient_limit_when_planning_then_fails_closed(
    test_case: RetentionPlanningErrorTestCase,
) -> None:
    adapter: Mock = Mock(adapter_name=BuiltinAdapter.SNOWFLAKE.value)
    runtime, warehouse, scope = build_retention_planner_inputs(
        adapter=adapter,
        desired_days=test_case.desired_days,
        existing_relations={},
        config_values={},
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        plan_retention(runtime=runtime, warehouse=warehouse, scope=scope)


@pytest.mark.parametrize(
    "test_case",
    [
        RetentionPlanningErrorTestCase(
            description="existing transient Snowflake relation above limit",
            desired_days=30,
            expected_error_fragment="transient tables cannot retain",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_transient_snowflake_relation_above_limit_when_planning_then_fails_closed(
    test_case: RetentionPlanningErrorTestCase,
) -> None:
    adapter: Mock = Mock(adapter_name=BuiltinAdapter.SNOWFLAKE.value)
    adapter.inspect_retention.return_value = RetentionState(
        request_id="orders",
        scope=RetentionScope.RELATION,
        configured_days=1,
        effective_days=1,
        is_transient=True,
    )
    runtime, warehouse, scope = build_retention_planner_inputs(
        adapter=adapter,
        desired_days=test_case.desired_days,
        existing_relations=_EXISTING_ORDERS,
        config_values={},
    )

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        plan_retention(runtime=runtime, warehouse=warehouse, scope=scope)


@pytest.mark.parametrize(
    "test_case",
    [
        PermanentRetentionPlanningTestCase(
            description="new explicit permanent table applies retention after creation",
            existing_relations={},
            observed_state=None,
            expected_direction=RetentionDirection.APPLY_AFTER_CREATE,
            expected_phase=RetentionPlanPhase.AFTER_CREATE,
            expected_statements=("ALTER RETENTION",),
        ),
        PermanentRetentionPlanningTestCase(
            description="transient target migration defers unsupported retention alter",
            existing_relations=_EXISTING_ORDERS,
            observed_state=RetentionState(
                request_id="orders",
                scope=RetentionScope.RELATION,
                configured_days=1,
                effective_days=1,
                is_transient=True,
            ),
            expected_direction=RetentionDirection.APPLY_AFTER_CREATE,
            expected_phase=RetentionPlanPhase.AFTER_CREATE,
            expected_statements=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_permanent_table_when_planning_long_retention_then_defers_until_migration(
    test_case: PermanentRetentionPlanningTestCase,
) -> None:
    adapter: Mock = Mock(adapter_name=BuiltinAdapter.SNOWFLAKE.value)
    adapter.inspect_retention.return_value = test_case.observed_state
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(
            phase=RetentionChangePhase.ALTER,
            statements=("ALTER RETENTION",),
        ),
    )
    runtime, warehouse, scope = build_retention_planner_inputs(
        adapter=adapter,
        desired_days=30,
        existing_relations=test_case.existing_relations,
        config_values={"table_type": "permanent"},
    )

    entries: tuple[RetentionPlanEntry, ...] = plan_retention(
        runtime=runtime,
        warehouse=warehouse,
        scope=scope,
    )

    assert entries[0].direction == test_case.expected_direction
    assert entries[0].phase == test_case.expected_phase
    assert entries[0].statements == test_case.expected_statements
