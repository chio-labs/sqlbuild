from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import LifeCycleEvent
from sqlbuild.executor.custom.models import MaterializationContext, PrepareVersionContext
from tests.unit.src.sqlbuild.executor.custom._test_types import (
    CustomContextExecutionTestCase,
    CustomContextQualificationTestCase,
)
from tests.unit.src.sqlbuild.executor.custom.helpers import (
    OrderingStatementRecorder,
    RecordingCustomAdapter,
    build_materialization_context,
    build_prepare_version_context,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CustomContextExecutionTestCase(
            description="materialization context records before adapter execution",
            context_builder=build_materialization_context,
            sql="CREATE TABLE scratch_orders AS SELECT 1",
            expected_result="materialization-result",
            expected_operation_order=("record", "execute"),
            expected_recorded_sql="CREATE TABLE scratch_orders AS SELECT 1",
        ),
        CustomContextExecutionTestCase(
            description="prepare version context records before adapter execution",
            context_builder=build_prepare_version_context,
            sql="INSERT INTO scratch_orders SELECT 1",
            expected_result="prepare-result",
            expected_operation_order=("record", "execute"),
            expected_recorded_sql="INSERT INTO scratch_orders SELECT 1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_custom_context_when_executing_sql_then_records_before_adapter_call(
    test_case: CustomContextExecutionTestCase,
) -> None:
    operation_order: list[str] = []
    adapter: RecordingCustomAdapter = RecordingCustomAdapter(
        operation_order=operation_order,
        execute_result=test_case.expected_result,
    )
    connection: object = object()
    recorder: OrderingStatementRecorder = OrderingStatementRecorder(operation_order=operation_order)
    context: MaterializationContext | PrepareVersionContext = test_case.context_builder(
        adapter=adapter,
        connection=connection,
        statement_recorder=recorder,
    )

    result: object = context.execute_sql(test_case.sql)

    events: tuple[LifeCycleEvent, ...] = recorder.snapshot()
    assert result == test_case.expected_result
    assert tuple(operation_order) == test_case.expected_operation_order
    assert tuple(event.content for event in events) == (test_case.expected_recorded_sql,)
    assert adapter.executed_connection is connection
    assert adapter.executed_sql == test_case.sql


@pytest.mark.parametrize(
    "test_case",
    [
        CustomContextQualificationTestCase(
            description="materialization context uses destination qualification",
            context_builder=build_materialization_context,
            name="order_state",
            database=None,
            schema=None,
            expected_qualified_name="warehouse.analytics.order_state",
        ),
        CustomContextQualificationTestCase(
            description="prepare version context uses destination qualification",
            context_builder=build_prepare_version_context,
            name="order_state",
            database=None,
            schema=None,
            expected_qualified_name="warehouse.analytics.order_state",
        ),
        CustomContextQualificationTestCase(
            description="materialization context uses explicit qualification",
            context_builder=build_materialization_context,
            name="order_state",
            database="archive",
            schema="history",
            expected_qualified_name="archive.history.order_state",
        ),
        CustomContextQualificationTestCase(
            description="prepare version context uses explicit qualification",
            context_builder=build_prepare_version_context,
            name="order_state",
            database="archive",
            schema="history",
            expected_qualified_name="archive.history.order_state",
        ),
        CustomContextQualificationTestCase(
            description="materialization context preserves qualified input",
            context_builder=build_materialization_context,
            name="external.order_state",
            database="archive",
            schema="history",
            expected_qualified_name="external.order_state",
        ),
        CustomContextQualificationTestCase(
            description="prepare version context preserves qualified input",
            context_builder=build_prepare_version_context,
            name="external.order_state",
            database="archive",
            schema="history",
            expected_qualified_name="external.order_state",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_custom_context_when_qualifying_relation_then_preserves_context_behavior(
    test_case: CustomContextQualificationTestCase,
) -> None:
    adapter: RecordingCustomAdapter = RecordingCustomAdapter(
        operation_order=[],
        execute_result=object(),
    )
    context: MaterializationContext | PrepareVersionContext = test_case.context_builder(
        adapter=adapter,
        connection=object(),
        statement_recorder=StatementRecorder(),
    )

    qualified_name: str = context.qualify_name(
        name=test_case.name,
        database=test_case.database,
        schema=test_case.schema,
    )

    assert qualified_name == test_case.expected_qualified_name
