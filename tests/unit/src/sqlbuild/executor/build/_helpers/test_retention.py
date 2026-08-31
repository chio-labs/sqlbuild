from __future__ import annotations

from unittest.mock import Mock, call

import pytest

from sqlbuild.adapter.contract.models import (
    RelationInfo,
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import PlanOutput, RetentionPlanEntry, TableTypePlanEntry
from sqlbuild.compiler.planner.types import (
    RetentionDirection,
    RetentionPlanPhase,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.build._helpers.retention import (
    apply_retention_phase,
    apply_table_type_conversions,
    reconcile_model_retention,
)
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    BuildModelRetentionReconciliationTestCase,
    BuildRetentionPhaseTestCase,
    TableTypeConversionErrorTestCase,
    TableTypeConversionTestCase,
)

_TARGET: RelationInfo = RelationInfo(
    database="warehouse",
    schema="analytics",
    name="orders",
    relation_type="BASE TABLE",
    is_transient=False,
)
_TRANSIENT_TARGET: RelationInfo = RelationInfo(
    database="warehouse",
    schema="analytics",
    name="orders",
    relation_type="BASE TABLE",
    is_transient=True,
)
_COPY: RelationInfo = RelationInfo(
    database="warehouse",
    schema="analytics",
    name="__sqb_type_swap__orders",
    relation_type="BASE TABLE",
    is_transient=False,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildRetentionPhaseTestCase(
            description="pre phase executes increases only",
            phase=RetentionPlanPhase.PRE,
            expected_statements=("PRE 1", "PRE 2"),
        ),
        BuildRetentionPhaseTestCase(
            description="post phase executes decreases only",
            phase=RetentionPlanPhase.POST,
            expected_statements=("POST 1",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_retention_plan_when_applying_phase_then_executes_only_ordered_phase_statements(
    test_case: BuildRetentionPhaseTestCase,
) -> None:
    adapter: Mock = Mock()
    connection: object = object()
    request: RetentionRequest = RetentionRequest(
        request_id="orders",
        scope=RetentionScope.RELATION,
        database=None,
        schema="analytics",
        name="orders",
        desired_days=7,
    )
    plan: PlanOutput = PlanOutput(
        retention_entries=(
            RetentionPlanEntry(
                request=request,
                model_names=("orders",),
                actual_days=1,
                effective_days=1,
                source="model",
                direction=RetentionDirection.INCREASE,
                phase=RetentionPlanPhase.PRE,
                statements=("PRE 1", "PRE 2"),
            ),
            RetentionPlanEntry(
                request=request,
                model_names=("orders",),
                actual_days=30,
                effective_days=30,
                source="model",
                direction=RetentionDirection.DECREASE,
                phase=RetentionPlanPhase.POST,
                statements=("POST 1",),
            ),
        )
    )

    apply_retention_phase(
        plan=plan,
        adapter=adapter,
        connection=connection,
        phase=test_case.phase,
    )

    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        BuildModelRetentionReconciliationTestCase(
            description="relation increase is applied after model creation",
            desired_days=7,
            effective_days=1,
            change_phase=RetentionChangePhase.PREPARE,
            expected_statements=("ALTER RETENTION 7",),
        ),
        BuildModelRetentionReconciliationTestCase(
            description="relation decrease waits for full build success",
            desired_days=1,
            effective_days=7,
            change_phase=RetentionChangePhase.FINALIZE,
            expected_statements=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_successful_model_when_reconciling_retention_then_defers_decreases(
    test_case: BuildModelRetentionReconciliationTestCase,
) -> None:
    request: RetentionRequest = RetentionRequest(
        request_id="orders",
        scope=RetentionScope.RELATION,
        database=None,
        schema="analytics",
        name="orders",
        desired_days=test_case.desired_days,
    )
    plan: PlanOutput = PlanOutput(
        retention_entries=(
            RetentionPlanEntry(
                request=request,
                model_names=("orders",),
                actual_days=None,
                effective_days=None,
                source="model",
                direction=RetentionDirection.APPLY_AFTER_CREATE,
                phase=RetentionPlanPhase.AFTER_CREATE,
            ),
        )
    )
    adapter: Mock = Mock()
    adapter.inspect_retention.return_value = RetentionState(
        request_id="orders",
        scope=RetentionScope.RELATION,
        configured_days=test_case.effective_days,
        effective_days=test_case.effective_days,
    )
    adapter.render_retention_changes.return_value = (
        RenderedRetentionChange(
            phase=test_case.change_phase,
            statements=("ALTER RETENTION 7",),
        ),
    )
    connection: object = object()

    reconcile_model_retention(
        plan=plan,
        adapter=adapter,
        connection=connection,
        model_name="orders",
    )

    assert adapter.execute.call_args_list == [
        call(connection=connection, sql=statement) for statement in test_case.expected_statements
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeConversionTestCase(
            description="undesired target with stale copy recreates before swap",
            relation_snapshots=(
                (_TRANSIENT_TARGET, _COPY),
                (_COPY,),
            ),
            expected_statements=(
                "CREATE OR REPLACE TABLE warehouse.analytics.__sqb_type_swap__orders AS SELECT * "
                "FROM warehouse.analytics.orders",
                "ALTER TABLE warehouse.analytics.orders SWAP WITH "
                "warehouse.analytics.__sqb_type_swap__orders",
                "DROP TABLE IF EXISTS warehouse.analytics.__sqb_type_swap__orders",
            ),
        ),
        TableTypeConversionTestCase(
            description="desired target with leftover copy only cleans copy",
            relation_snapshots=((_TARGET, _COPY),),
            expected_statements=(
                "DROP TABLE IF EXISTS warehouse.analytics.__sqb_type_swap__orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recoverable_table_type_state_when_converting_then_uses_inspection_only_recovery(
    test_case: TableTypeConversionTestCase,
) -> None:
    adapter: Mock = Mock()
    adapter.render_qualified_name.side_effect = lambda *, database, schema, name: ".".join(
        (database, schema, name)
    )
    adapter.list_relations.side_effect = test_case.relation_snapshots
    connection: object = object()
    entry: TableTypePlanEntry = TableTypePlanEntry(
        model_name="orders",
        destination=CompiledRelationLocation(
            database="warehouse",
            schema="analytics",
            name="orders",
            qualified_name="warehouse.analytics.orders",
        ),
        copy_name="__sqb_type_swap__orders",
        desired_type="permanent",
        actual_type="transient",
        source="model",
        downgrade=False,
        downgrade_policy="require_confirmation",
    )

    apply_table_type_conversions(
        plan=PlanOutput(table_type_entries=(entry,)), adapter=adapter, connection=connection
    )

    assert tuple(item.kwargs["sql"] for item in adapter.execute.call_args_list) == (
        test_case.expected_statements
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeConversionTestCase(
            description="unknown live metadata fails before SQL",
            relation_snapshots=(
                (
                    RelationInfo(
                        database="warehouse",
                        schema="analytics",
                        name="orders",
                        relation_type="BASE TABLE",
                    ),
                ),
            ),
            expected_statements=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_live_table_type_when_converting_then_fails_closed(
    test_case: TableTypeConversionTestCase,
) -> None:
    adapter: Mock = Mock()
    adapter.render_qualified_name.side_effect = lambda *, database, schema, name: ".".join(
        (database, schema, name)
    )
    adapter.list_relations.side_effect = test_case.relation_snapshots
    entry: TableTypePlanEntry = TableTypePlanEntry(
        model_name="orders",
        destination=CompiledRelationLocation(
            database="warehouse",
            schema="analytics",
            name="orders",
            qualified_name="warehouse.analytics.orders",
        ),
        copy_name="__sqb_type_swap__orders",
        desired_type="permanent",
        actual_type=None,
        source="model",
        downgrade=False,
        downgrade_policy="require_confirmation",
    )

    with pytest.raises(ExecutorInputError, match="metadata is unknown"):
        apply_table_type_conversions(
            plan=PlanOutput(table_type_entries=(entry,)), adapter=adapter, connection=object()
        )

    assert tuple(item.kwargs["sql"] for item in adapter.execute.call_args_list) == (
        test_case.expected_statements
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeConversionErrorTestCase(
            description="missing target fails before SQL",
            relation_snapshots=((),),
            expected_error_fragment="target no longer exists",
            expected_statements=(),
        ),
        TableTypeConversionErrorTestCase(
            description="wrong copy type fails before swap",
            relation_snapshots=(
                (_TRANSIENT_TARGET,),
                (
                    RelationInfo(
                        database="warehouse",
                        schema="analytics",
                        name="__sqb_type_swap__orders",
                        relation_type="BASE TABLE",
                        is_transient=True,
                    ),
                ),
            ),
            expected_error_fragment="not created with the desired type",
            expected_statements=(
                "CREATE OR REPLACE TABLE warehouse.analytics.__sqb_type_swap__orders AS SELECT * "
                "FROM warehouse.analytics.orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unrecoverable_table_type_state_when_converting_then_fails_before_swap(
    test_case: TableTypeConversionErrorTestCase,
) -> None:
    adapter: Mock = Mock()
    adapter.render_qualified_name.side_effect = lambda *, database, schema, name: ".".join(
        (database, schema, name)
    )
    adapter.list_relations.side_effect = test_case.relation_snapshots
    entry: TableTypePlanEntry = TableTypePlanEntry(
        model_name="orders",
        destination=CompiledRelationLocation(
            database="warehouse",
            schema="analytics",
            name="orders",
            qualified_name="warehouse.analytics.orders",
        ),
        copy_name="__sqb_type_swap__orders",
        desired_type="permanent",
        actual_type="transient",
        source="model",
        downgrade=False,
        downgrade_policy="require_confirmation",
    )

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        apply_table_type_conversions(
            plan=PlanOutput(table_type_entries=(entry,)), adapter=adapter, connection=object()
        )

    assert tuple(item.kwargs["sql"] for item in adapter.execute.call_args_list) == (
        test_case.expected_statements
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
