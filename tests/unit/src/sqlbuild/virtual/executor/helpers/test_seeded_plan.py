from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.planner.models import CursorBounds, CursorOverrides, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction
from sqlbuild.virtual.executor.helpers.seeded_plan import build_virtual_execution_plan
from sqlbuild.virtual.executor.models import VirtualBuildExecutionPlan
from tests.unit.src.sqlbuild.virtual.executor.helpers._test_types import (
    SeededPlanAdaptationTestCase,
    SeededPlanBoundsPrecedenceTestCase,
    SeededPlanNoAdaptationTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor.helpers.helpers import (
    build_adapter,
    build_bound_physical_relation,
    build_optional_bound_physical_relations,
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

NO_ADAPTATION_TEST_CASES: list[SeededPlanNoAdaptationTestCase] = [
    SeededPlanNoAdaptationTestCase(
        description="same version hash does not adapt",
        incremental_strategy="delete_insert",
        bound_version_hash="newhash123456",
        expected_version_hash="newhash123456",
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.CREATE_TABLE,
        cursor_bounds_enabled=True,
        expected_action=PlanAction.CREATE_TABLE,
        unexpected_sql_fragment="__sqlbuild_cursor_bounded",
    ),
    SeededPlanNoAdaptationTestCase(
        description="missing bound physical relation does not adapt",
        incremental_strategy="delete_insert",
        bound_version_hash=None,
        expected_version_hash="newhash123456",
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.CREATE_TABLE,
        cursor_bounds_enabled=True,
        expected_action=PlanAction.CREATE_TABLE,
        unexpected_sql_fragment="__sqlbuild_cursor_bounded",
    ),
    SeededPlanNoAdaptationTestCase(
        description="non-incremental model does not adapt",
        incremental_strategy="delete_insert",
        bound_version_hash="oldhash123456",
        expected_version_hash="newhash123456",
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        cursor_bounds_enabled=True,
        expected_action=PlanAction.CREATE_TABLE,
        unexpected_sql_fragment="__sqlbuild_cursor_bounded",
    ),
    SeededPlanNoAdaptationTestCase(
        description="unsupported incremental strategy does not adapt",
        incremental_strategy="unknown_strategy",
        bound_version_hash="oldhash123456",
        expected_version_hash="newhash123456",
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.CREATE_TABLE,
        cursor_bounds_enabled=True,
        expected_action=PlanAction.CREATE_TABLE,
        unexpected_sql_fragment="__sqlbuild_cursor_bounded",
    ),
    SeededPlanNoAdaptationTestCase(
        description="delete-insert without bounds stays unchanged",
        incremental_strategy="delete_insert",
        bound_version_hash="oldhash123456",
        expected_version_hash="newhash123456",
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.CREATE_TABLE,
        cursor_bounds_enabled=False,
        expected_action=PlanAction.CREATE_TABLE,
        unexpected_sql_fragment="__sqlbuild_cursor_bounded",
    ),
]

BOUNDS_PRECEDENCE_TEST_CASES: list[SeededPlanBoundsPrecedenceTestCase] = [
    SeededPlanBoundsPrecedenceTestCase(
        description="cursor overrides are used when entry bounds are absent",
        entry_bounds_enabled=False,
        expected_sql_fragment="2026-01-10T00:00:00",
        unexpected_sql_fragment="2026-01-02T00:00:00",
    ),
    SeededPlanBoundsPrecedenceTestCase(
        description="entry bounds win over cursor overrides",
        entry_bounds_enabled=True,
        expected_sql_fragment="2026-01-02T00:00:00",
        unexpected_sql_fragment="2026-01-10T00:00:00",
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_seeded_virtual_incremental_plan_when_adapting_then_it_restores_bounds(
    test_case: SeededPlanAdaptationTestCase,
) -> None:
    plan_output: PlanOutput = build_seeded_incremental_plan_output(
        incremental_strategy=test_case.incremental_strategy
    )

    adapted: VirtualBuildExecutionPlan = build_virtual_execution_plan(
        adapter=build_adapter(),
        direct_plan_output=plan_output,
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

    adapted_entry: Any = adapted.execution_model_entries[0]
    assert adapted_entry.action == test_case.expected_action
    assert test_case.expected_sql_fragment in adapted_entry.resolved_sql
    assert adapted.direct_plan_output.model_entries[0].action == PlanAction.CREATE_TABLE
    assert adapted.display_plan_output.model_entries[0].action == test_case.expected_action


@pytest.mark.parametrize(
    "test_case",
    NO_ADAPTATION_TEST_CASES,
    ids=[case.description for case in NO_ADAPTATION_TEST_CASES],
)
def test_given_seeded_virtual_plan_that_should_not_adapt_when_adapting_then_it_stays_unchanged(
    test_case: SeededPlanNoAdaptationTestCase,
) -> None:
    plan_output: PlanOutput = build_seeded_incremental_plan_output(
        incremental_strategy=test_case.incremental_strategy,
        materialization_type=test_case.materialization_type,
        action=test_case.action,
        include_cursor_bounds=test_case.cursor_bounds_enabled,
    )
    adapted: VirtualBuildExecutionPlan = build_virtual_execution_plan(
        adapter=build_adapter(),
        direct_plan_output=plan_output,
        bound_physical_relations=build_optional_bound_physical_relations(
            model_name="orders", version_hash=test_case.bound_version_hash
        ),
        expected_version_hashes={"orders": test_case.expected_version_hash},
        cursor_overrides=None,
    )

    adapted_entry: Any = adapted.execution_model_entries[0]
    assert adapted_entry.action == test_case.expected_action
    assert adapted_entry.resolved_sql == plan_output.model_entries[0].resolved_sql
    assert test_case.unexpected_sql_fragment not in adapted_entry.resolved_sql
    assert adapted.display_plan_output is plan_output


@pytest.mark.parametrize(
    "test_case",
    BOUNDS_PRECEDENCE_TEST_CASES,
    ids=[case.description for case in BOUNDS_PRECEDENCE_TEST_CASES],
)
def test_given_seeded_virtual_plan_with_cursor_overrides_when_adapting_then_uses_expected_bounds(
    test_case: SeededPlanBoundsPrecedenceTestCase,
) -> None:
    plan_output: PlanOutput = build_seeded_incremental_plan_output(
        incremental_strategy="delete_insert",
        cursor_bounds=(
            CursorBounds(start="2026-01-02T00:00:00", end="2026-01-04T00:00:00")
            if test_case.entry_bounds_enabled
            else None
        ),
        include_cursor_bounds=test_case.entry_bounds_enabled,
    )

    adapted: VirtualBuildExecutionPlan = build_virtual_execution_plan(
        adapter=build_adapter(),
        direct_plan_output=plan_output,
        bound_physical_relations={
            "orders": build_bound_physical_relation(
                model_name="orders", version_hash="oldhash123456"
            )
        },
        expected_version_hashes={"orders": "newhash123456"},
        cursor_overrides=CursorOverrides(
            start_ts="2026-01-10T00:00:00",
            end_ts="2026-01-12T00:00:00",
        ),
    )

    adapted_entry: Any = adapted.execution_model_entries[0]
    assert adapted_entry.action == PlanAction.INCREMENTAL_DELETE_INSERT
    assert test_case.expected_sql_fragment in adapted_entry.resolved_sql
    assert test_case.unexpected_sql_fragment not in adapted_entry.resolved_sql
