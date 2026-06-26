from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneStatus
from tests.unit.src.sqlbuild.executor.clone.helpers.helpers import (
    FakeCloneAdapter,
    build_clone_model_entry,
)
from tests.unit.src.sqlbuild.executor.clone.main._test_types import CloneStreamTestCase


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
    ids=["streams one on_item callback per relation with position and flow"],
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

    def _on_item(index: int, total: int, item: CloneItemResult) -> None:
        streamed.append((index, total, item.destination_relation, item.status.value))

    result: CloneExecutionResult = execute_clone(
        origin_model_entries=origin_entries,
        destination_model_entries=destination_entries,
        origin_seed_entries=(),
        destination_seed_entries=(),
        adapter=adapter,
        origin_connection=object(),
        destination_connection=object(),
        hard_copy=False,
        on_item=_on_item,
    )

    assert tuple((index, total) for index, total, *_ in streamed) == test_case.expected_positions
    assert tuple(destination for *_, destination, _ in streamed) == (
        test_case.expected_destination_relations
    )
    assert all(status == CloneStatus.SUCCESS.value for *_, status in streamed)
    assert len(result.item_results) == len(test_case.model_names)
