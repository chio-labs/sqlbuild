"""Tests for plan-entry cursor override handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.output.plan_entry import _compute_plan_cursor_bounds
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    ModelCursorSnapshot,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import BackfillAction
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    PlanEntryCursorGrainTestCase,
    PlanEntryCursorOverrideTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanEntryCursorOverrideTestCase(
            description="explicit overrides advance the inclusive end to an exclusive bound",
            start_cursor_override="2026-01-02T00:00:00",
            end_cursor_override="2026-01-04T00:00:00",
            expected_bounds=CursorBounds(
                start="2026-01-02T00:00:00",
                end="2026-01-04T00:00:01",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_cursor_overrides_without_snapshot_when_planning_then_uses_overrides(
    test_case: PlanEntryCursorOverrideTestCase,
) -> None:
    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        deps=(),
        name="orders",
        relative_path=Path("models/orders.sql"),
        query_sql="SELECT 1",
        references=(),
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "cursor": "ordered_at",
                "cursor_type": "timestamp",
            }
        ),
        destination=CompiledRelationLocation(
            database=None,
            schema="dev__physical",
            name="orders__v_123",
            qualified_name="dev__physical.orders__v_123",
        ),
    )

    bounds: CursorBounds | None = _compute_plan_cursor_bounds(
        model=model,
        snapshot=WarehouseSnapshot(),
        backfill=BackfillResult(action=BackfillAction.BOUNDED, duration="7d"),
        full_refresh=False,
        start_cursor_override=test_case.start_cursor_override,
        end_cursor_override=test_case.end_cursor_override,
        runtime_owned_cursor_bounds=False,
    )

    assert bounds == test_case.expected_bounds


@pytest.mark.parametrize(
    "test_case",
    [
        PlanEntryCursorGrainTestCase(
            description="hour grain advances plan DML bound by a whole hour",
            cursor_grain="hour",
            upstream_max="2026-01-04T12:37:00",
            expected_end="2026-01-04T13:37:00",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_cursor_grain_when_planning_then_dml_bound_matches_query_interval(
    test_case: PlanEntryCursorGrainTestCase,
) -> None:
    model: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        deps=(),
        name="orders",
        relative_path=Path("models/orders.sql"),
        query_sql="SELECT 1",
        references=(),
        config=CompileModelConfig(
            values={
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "cursor": "ordered_at",
                "cursor_type": "timestamp",
                "cursor_grain": test_case.cursor_grain,
            }
        ),
        destination=CompiledRelationLocation(
            database=None,
            schema="dev__physical",
            name="orders__v_123",
            qualified_name="dev__physical.orders__v_123",
        ),
    )

    bounds: CursorBounds | None = _compute_plan_cursor_bounds(
        model=model,
        snapshot=WarehouseSnapshot(
            cursor_snapshots={
                "orders": ModelCursorSnapshot(
                    target_max="2026-01-04T11:00:00",
                    upstream_mins=("2026-01-01T00:00:00",),
                    upstream_maxes=(test_case.upstream_max,),
                )
            }
        ),
        backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
        full_refresh=False,
        start_cursor_override=None,
        end_cursor_override=None,
        runtime_owned_cursor_bounds=False,
    )

    assert bounds is not None
    assert bounds.end == test_case.expected_end
