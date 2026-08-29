from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.compiler.planner.models import FunctionPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.models import (
    CloneExecutionInput,
    CloneExecutionResult,
    CloneItemResult,
    CloneSourceEntries,
)
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.executor.clone._helpers.helpers import (
    FakeCloneAdapter,
    build_clone_function_entry,
    build_clone_model_entry,
)
from tests.unit.src.sqlbuild.executor.clone.main._test_types import (
    CloneStreamTestCase,
    InterleavedCloneGraphTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneStreamTestCase(
            description="streams one on_item callback per relation with position and flow",
            model_names=("orders", "payments", "customers"),
            origin_schema="prod",
            destination_schema="dev",
            expected_positions=((1, 3), (2, 3), (3, 3)),
            expected_destination_relations=(
                "dev.orders",
                "dev.payments",
                "dev.customers",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_entries_when_executing_then_streams_each_item(
    test_case: CloneStreamTestCase,
) -> None:
    adapter: FakeCloneAdapter = FakeCloneAdapter(
        supports_zero_copy=True, origin_names=test_case.model_names
    )
    origin_entries: tuple[ModelPlanEntry, ...] = tuple(
        build_clone_model_entry(schema=test_case.origin_schema, name=name)
        for name in test_case.model_names
    )
    destination_entries: tuple[ModelPlanEntry, ...] = tuple(
        build_clone_model_entry(schema=test_case.destination_schema, name=name)
        for name in test_case.model_names
    )
    streamed: list[tuple[int, int, str | None, str]] = []

    def _on_item(index: int, *, total: int, item: CloneItemResult) -> None:
        streamed.append((index, total, item.destination_relation, item.status.value))

    result: CloneExecutionResult = execute_clone(
        inputs=CloneExecutionInput(
            source_entries=CloneSourceEntries(),
            origin_model_entries=origin_entries,
            destination_model_entries=destination_entries,
            origin_seed_entries=(),
            destination_seed_entries=(),
            destination_function_entries=(),
            execution_order=tuple(entry.key for entry in destination_entries),
            adapter=adapter,
            origin_connection=object(),
            destination_connection=object(),
            hard_copy=False,
            run_id="clone-run",
            query_change_tracking=False,
            on_item=_on_item,
        )
    )

    assert tuple((index, total) for index, total, *_ in streamed) == test_case.expected_positions
    assert tuple(destination for *_, destination, _ in streamed) == (
        test_case.expected_destination_relations
    )
    assert all(status == CloneStatus.SUCCESS.value for *_, status in streamed)
    assert len(result.item_results) == len(test_case.model_names)


@pytest.mark.parametrize(
    "test_case",
    (
        InterleavedCloneGraphTestCase(
            description="executes interleaved relations and functions in dependency order",
            expected_names=("orders", "add_one", "enriched_orders"),
            expected_actions=(
                CloneAction.CLONED,
                CloneAction.RECREATED_FUNCTION,
                CloneAction.RECREATED_VIEW,
            ),
            expected_function_statement="CREATE FUNCTION dev.add_one",
            expected_view_statement_fragment="VIEW dev.enriched_orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_interleaved_clone_graph_when_executing_then_uses_plan_order(
    test_case: InterleavedCloneGraphTestCase,
) -> None:
    adapter: FakeCloneAdapter = FakeCloneAdapter(
        supports_zero_copy=True,
        origin_names=("orders", "enriched_orders"),
    )
    origin_table: ModelPlanEntry = build_clone_model_entry(schema="prod", name="orders")
    origin_view: ModelPlanEntry = replace(
        build_clone_model_entry(schema="prod", name="enriched_orders"),
        materialization_type=MaterializationType.VIEW,
    )
    destination_table: ModelPlanEntry = build_clone_model_entry(schema="dev", name="orders")
    destination_view: ModelPlanEntry = replace(
        build_clone_model_entry(schema="dev", name="enriched_orders"),
        materialization_type=MaterializationType.VIEW,
        resolved_sql="SELECT dev.add_one(*) FROM dev.orders",
    )
    function: FunctionPlanEntry = build_clone_function_entry(schema="dev", name="add_one")

    result: CloneExecutionResult = execute_clone(
        inputs=CloneExecutionInput(
            source_entries=CloneSourceEntries(),
            origin_model_entries=(origin_table, origin_view),
            destination_model_entries=(destination_view, destination_table),
            origin_seed_entries=(),
            destination_seed_entries=(),
            destination_function_entries=(function,),
            execution_order=(destination_table.key, function.key, destination_view.key),
            adapter=adapter,
            origin_connection=object(),
            destination_connection=object(),
            hard_copy=False,
            run_id="clone-run",
            query_change_tracking=False,
        )
    )

    assert tuple(item.name for item in result.item_results) == test_case.expected_names
    assert tuple(item.action for item in result.item_results) == test_case.expected_actions
    executed_sql: str = "\n".join(adapter.executed_statements)
    function_statement_index: int = executed_sql.index(test_case.expected_function_statement)
    view_statement_index: int = executed_sql.index(test_case.expected_view_statement_fragment)
    assert function_statement_index < view_statement_index
