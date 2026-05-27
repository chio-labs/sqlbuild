from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.planner.types import PlanAction
from sqlbuild.virtual.executor.helpers.seeded_plan import (
    adapt_plan_for_seeded_virtual_execution,
)
from tests.unit.src.sqlbuild.virtual.executor.helpers._test_types import (
    SeededPlanAdaptationTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor.helpers.helpers import (
    build_adapter,
    build_bound_physical_relation,
    build_seeded_incremental_plan_output,
)

TEST_CASES: list[SeededPlanAdaptationTestCase] = [
    SeededPlanAdaptationTestCase(
        description="delete_insert create-table plan restores incremental action and bounded sql",
        incremental_strategy="delete_insert",
        expected_action=PlanAction.INCREMENTAL_DELETE_INSERT,
        expected_sql_fragment='WHERE "ordered_at" >= TIMESTAMP',
    ),
    SeededPlanAdaptationTestCase(
        description="append create-table plan restores incremental action and bounded sql",
        incremental_strategy="append",
        expected_action=PlanAction.INCREMENTAL_APPEND,
        expected_sql_fragment='AND "ordered_at" < TIMESTAMP',
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_seeded_virtual_incremental_plan_when_adapting_then_it_restores_bounds(
    test_case: SeededPlanAdaptationTestCase,
) -> None:
    plan_output: PlanOutput = build_seeded_incremental_plan_output(
        incremental_strategy=test_case.incremental_strategy
    )

    adapted: PlanOutput = adapt_plan_for_seeded_virtual_execution(
        adapter=build_adapter(),
        plan_output=plan_output,
        bound_physical_relations={
            "orders": build_bound_physical_relation(
                model_name="orders", version_hash="oldhash123456"
            )
        },
        expected_version_hashes={"orders": "newhash123456"},
        cursor_overrides=CursorOverrides(
            start_ts="2026-01-02T00:00:00",
            end_ts="2026-01-04T00:00:00",
        ),
    )

    adapted_entry: Any = adapted.model_entries[0]
    assert adapted_entry.action == test_case.expected_action
    assert test_case.expected_sql_fragment in adapted_entry.resolved_sql
