"""Tests for planner-owned microbatch limit decisions."""

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.output.plan_entry import _apply_microbatch_limit
from sqlbuild.compiler.planner.models import CursorBounds, ModelPlanEntry, PlanWarning
from sqlbuild.compiler.planner.types import (
    IncrementalMode,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.spec.contracts.types import MicrobatchLimitAction
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    MicrobatchLimitPlanningErrorTestCase,
    MicrobatchLimitPlanningTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchLimitPlanningTestCase(
            description="warn preserves complete planner-owned range",
            max_batches=2,
            action="warn",
            expected_count=3,
            expected_warning=True,
        ),
        MicrobatchLimitPlanningTestCase(
            description="numeric override permits intentional backfill",
            max_batches=3,
            action="error",
            expected_count=3,
            expected_warning=False,
        ),
        MicrobatchLimitPlanningTestCase(
            description="skipped model does not apply error limit",
            max_batches=1,
            action="error",
            expected_count=None,
            expected_warning=False,
            plan_action="skip",
        ),
        MicrobatchLimitPlanningTestCase(
            description="equal-bound full refresh is one batch",
            max_batches=1,
            action="error",
            expected_count=1,
            expected_warning=False,
            plan_action="create_table",
            range_start="10",
            range_end="10",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_planner_owned_range_when_applying_limit_then_expected_decision_is_preserved(
    test_case: MicrobatchLimitPlanningTestCase,
) -> None:
    entry: ModelPlanEntry = ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="events"),
        name="events",
        relative_path=Path("models/events.sql"),
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction(test_case.plan_action),
        reason=PlanReason.NORMAL_INCREMENTAL,
        destination=CompiledRelationLocation(None, "main", "events", "main.events"),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl="",
        incremental_mode=IncrementalMode.MICROBATCH,
        cursor_type="integer",
        batch_size="10",
        microbatch_range=CursorBounds(start=test_case.range_start, end=test_case.range_end),
    )
    action: MicrobatchLimitAction = MicrobatchLimitAction(test_case.action)

    limited_entry, warning = _apply_microbatch_limit(
        entry=entry, max_batches=test_case.max_batches, action=action
    )

    assert limited_entry.microbatch_limit_count == test_case.expected_count
    assert (warning is not None) is test_case.expected_warning
    assert isinstance(warning, PlanWarning) is test_case.expected_warning


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchLimitPlanningErrorTestCase(
            description="error rejects planner-owned range",
            max_batches=2,
            action="error",
            expected_error_fragment="MICROBATCH LIMIT EXCEEDED",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_excess_planner_owned_range_when_action_is_error_then_planning_fails(
    test_case: MicrobatchLimitPlanningErrorTestCase,
) -> None:
    entry: ModelPlanEntry = ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="events"),
        name="events",
        relative_path=Path("models/events.sql"),
        materialization_type=MaterializationType.INCREMENTAL,
        action=PlanAction.INCREMENTAL_DELETE_INSERT,
        reason=PlanReason.NORMAL_INCREMENTAL,
        destination=CompiledRelationLocation(None, "main", "events", "main.events"),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl="",
        incremental_mode=IncrementalMode.MICROBATCH,
        cursor_type="integer",
        batch_size="10",
        microbatch_range=CursorBounds(start="0", end="30"),
    )

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        _apply_microbatch_limit(
            entry=entry,
            max_batches=test_case.max_batches,
            action=MicrobatchLimitAction(test_case.action),
        )
