from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.contract.types import PromotionStrategy
from sqlbuild.compiler.planner.types import OnSchemaChange
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.run._helpers.execution.promotion import promote_relation_to_destination
from sqlbuild.executor.run._helpers.execution.staging import create_staging_relation
from sqlbuild.executor.run._helpers.materializations.incremental import _apply_schema_change
from sqlbuild.observability import EventDispatcher, LifecycleEvent, dispatcher_scope
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    LifecycleProgressTestCase,
    PromotionProgressTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (LifecycleProgressTestCase("staging creation", ("operation_started", "operation_completed")),),
    ids=lambda case: case.description,
)
def test_given_staging_creation_when_adapter_blocks_then_start_is_already_dispatched(
    test_case: LifecycleProgressTestCase,
) -> None:
    events: list[LifecycleEvent] = []
    barrier_events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    adapter: Mock = Mock()
    context: Mock = Mock(adapter=adapter, connection=object())
    context.entry.table_type = "transient"
    adapter.drop.side_effect = lambda **_: barrier_events.append(events[-1])

    with dispatcher_scope(dispatcher):
        create_staging_relation(
            context=context,
            staging_qualified="analytics.orders__staging",
            resolved_sql="SELECT 1",
            statement_recorder=StatementRecorder(),
        )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert barrier_events[0].event_type == "operation_started"


@pytest.mark.parametrize(
    "test_case",
    (
        LifecycleProgressTestCase(
            "schema synchronization", ("operation_started", "operation_completed")
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_schema_drift_when_sync_blocks_then_start_is_already_dispatched(
    test_case: LifecycleProgressTestCase,
) -> None:
    events: list[LifecycleEvent] = []
    barrier_events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    adapter: Mock = Mock()
    adapter.add_columns.side_effect = lambda **_: barrier_events.append(events[-1])

    with dispatcher_scope(dispatcher):
        _apply_schema_change(
            adapter=adapter,
            connection=object(),
            target_qualified="analytics.orders",
            target_columns=(ColumnInfo(name="id", type="INTEGER"),),
            delta_columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="amount", type="INTEGER"),
            ),
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            statement_recorder=StatementRecorder(),
        )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert barrier_events[0].event_type == "operation_started"
    assert events[-1].payload["metadata"] == {
        "added_count": 1,
        "altered_count": 0,
        "changed_count": 1,
        "removed_count": 0,
    }


@pytest.mark.parametrize(
    "test_case",
    (
        LifecycleProgressTestCase(
            "relation promotion", ("operation_started", "operation_completed")
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relation_promotion_when_inspection_blocks_then_start_is_already_dispatched(
    test_case: LifecycleProgressTestCase,
) -> None:
    events: list[LifecycleEvent] = []
    barrier_events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    adapter: Mock = Mock()
    adapter.relation_exists.side_effect = lambda **_: (barrier_events.append(events[-1]), False)[1]

    with dispatcher_scope(dispatcher):
        promote_relation_to_destination(
            adapter=adapter,
            connection=object(),
            origin_relation="analytics.orders__staging",
            destination_relation="analytics.orders",
            destination_database=None,
            destination_schema="analytics",
            destination_name="orders",
            statement_recorder=StatementRecorder(),
        )

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert barrier_events[0].event_type == "operation_started"
    assert "strategy" not in events[0].payload
    assert events[-1].payload["strategy"] == "rename"
    assert events[-1].payload["adapter"] == "custom"


@pytest.mark.parametrize(
    "test_case",
    (
        PromotionProgressTestCase(
            description="existing destination uses atomic swap",
            strategy="atomic_swap",
            expected_method="swap",
            expected_event_types=("operation_started", "operation_completed"),
        ),
        PromotionProgressTestCase(
            description="existing destination uses atomic replace",
            strategy="atomic_replace",
            expected_method="replace_table_from_relation",
            expected_event_types=("operation_started", "operation_completed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_existing_destination_when_promoting_then_terminal_records_actual_strategy(
    test_case: PromotionProgressTestCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    adapter: Mock = Mock(adapter_name="snowflake")
    adapter.relation_exists.return_value = True
    adapter.default_promotion_strategy.return_value = PromotionStrategy(test_case.strategy)

    with dispatcher_scope(dispatcher):
        promote_relation_to_destination(
            adapter=adapter,
            connection=object(),
            origin_relation="analytics.orders__staging",
            destination_relation="analytics.orders",
            destination_database=None,
            destination_schema="analytics",
            destination_name="orders",
            statement_recorder=StatementRecorder(),
        )

    getattr(adapter, test_case.expected_method).assert_called_once()
    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert "strategy" not in events[0].payload
    assert events[-1].payload["strategy"] == test_case.strategy


@pytest.mark.parametrize(
    "test_case",
    (
        PromotionProgressTestCase(
            description="unsupported catalogued strategy fails honestly",
            strategy="create_new",
            expected_method="relation_exists",
            expected_event_types=("operation_started", "operation_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsupported_strategy_when_promoting_then_failed_terminal_records_observation(
    test_case: PromotionProgressTestCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    adapter: Mock = Mock(adapter_name="snowflake")
    adapter.relation_exists.return_value = True
    adapter.default_promotion_strategy.return_value = PromotionStrategy(test_case.strategy)

    with dispatcher_scope(dispatcher), pytest.raises(ExecutorInputError, match="Unsupported"):
        promote_relation_to_destination(
            adapter=adapter,
            connection=object(),
            origin_relation="analytics.orders__staging",
            destination_relation="analytics.orders",
            destination_database=None,
            destination_schema="analytics",
            destination_name="orders",
            statement_recorder=StatementRecorder(),
        )

    getattr(adapter, test_case.expected_method).assert_called_once()
    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[-1].payload["strategy"] == test_case.strategy


@pytest.mark.parametrize(
    "test_case",
    (
        LifecycleProgressTestCase(
            "partial mutation failure", ("operation_started", "operation_failed")
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_partial_schema_mutation_when_later_call_fails_then_operation_fails(
    test_case: LifecycleProgressTestCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    adapter: Mock = Mock()
    adapter.drop_columns.side_effect = RuntimeError("reconciliation failed")

    with dispatcher_scope(dispatcher), pytest.raises(RuntimeError, match="reconciliation failed"):
        _apply_schema_change(
            adapter=adapter,
            connection=object(),
            target_qualified="analytics.orders",
            target_columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="old", type="INTEGER"),
            ),
            delta_columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="new", type="INTEGER"),
            ),
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            statement_recorder=StatementRecorder(),
        )

    adapter.add_columns.assert_called_once()
    assert tuple(event.event_type for event in events) == test_case.expected_event_types


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
