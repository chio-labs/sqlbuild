"""Typing of untyped --start-cursor/--end-cursor values from the selected models."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.resolve.cursor import type_cursor_overrides
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import CursorOverrides
from tests.unit.src.sqlbuild.compiler.planner._helpers.resolve._test_types import (
    UntypedCursorOverrideErrorTestCase,
    UntypedCursorOverrideTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.resolve.helpers import build_cursor_models


@pytest.mark.parametrize(
    "test_case",
    (
        UntypedCursorOverrideTestCase(
            description="timestamp selection",
            model_cursor_types=(("orders", "timestamp"), ("customers", None)),
            overrides=CursorOverrides(start="2026-05-01", end="2026-05-02T12:00:00"),
            expected_overrides=CursorOverrides(start_ts="2026-05-01", end_ts="2026-05-02T12:00:00"),
        ),
        UntypedCursorOverrideTestCase(
            description="integer selection",
            model_cursor_types=(("events", "integer"), ("event_rollup", "integer")),
            overrides=CursorOverrides(start="100"),
            expected_overrides=CursorOverrides(start_int="100"),
        ),
        UntypedCursorOverrideTestCase(
            description="no cursor model reads an integer literal as an integer",
            model_cursor_types=(),
            overrides=CursorOverrides(start="100", end="250"),
            expected_overrides=CursorOverrides(start_int="100", end_int="250"),
        ),
        UntypedCursorOverrideTestCase(
            description="no cursor model reads a date as a timestamp",
            model_cursor_types=(("customers", None),),
            overrides=CursorOverrides(end="2026-05-02"),
            expected_overrides=CursorOverrides(end_ts="2026-05-02"),
        ),
        UntypedCursorOverrideTestCase(
            description="typed overrides pass through a mixed selection",
            model_cursor_types=(("orders", "timestamp"), ("events", "integer")),
            overrides=CursorOverrides(start_ts="2026-05-01", end_int="9"),
            expected_overrides=CursorOverrides(start_ts="2026-05-01", end_int="9"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_untyped_cursor_values_when_typing_then_uses_the_selection_cursor_type(
    test_case: UntypedCursorOverrideTestCase,
) -> None:
    typed: CursorOverrides | None = type_cursor_overrides(
        cursor_overrides=test_case.overrides,
        selected_models=build_cursor_models(model_cursor_types=test_case.model_cursor_types),
    )

    assert typed == test_case.expected_overrides


@pytest.mark.parametrize(
    "test_case",
    (
        UntypedCursorOverrideErrorTestCase(
            description="mixed cursor types",
            model_cursor_types=(
                ("orders", "timestamp"),
                ("events", "integer"),
                ("payments", "timestamp"),
            ),
            overrides=CursorOverrides(start="2026-05-01"),
            expected_message_prefix=(
                "--start-cursor and --end-cursor need one cursor type, but the selection mixes "
                "integer cursor models (events) and timestamp cursor models (orders, payments)"
            ),
            expected_code="S303",
        ),
        UntypedCursorOverrideErrorTestCase(
            description="integer selection with a timestamp value",
            model_cursor_types=(("events", "integer"),),
            overrides=CursorOverrides(start="2026-05-01"),
            expected_message_prefix="--start-cursor value '2026-05-01' is not a valid integer",
            expected_code="S000",
        ),
        UntypedCursorOverrideErrorTestCase(
            description="timestamp selection with an invalid value",
            model_cursor_types=(("orders", "timestamp"),),
            overrides=CursorOverrides(end="yesterday"),
            expected_message_prefix="--end-cursor value 'yesterday' is not a valid ISO timestamp",
            expected_code="S000",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_untypable_cursor_values_when_typing_then_raises_planner_input_error(
    test_case: UntypedCursorOverrideErrorTestCase,
) -> None:
    with pytest.raises(PlannerInputError) as error:
        type_cursor_overrides(
            cursor_overrides=test_case.overrides,
            selected_models=build_cursor_models(model_cursor_types=test_case.model_cursor_types),
        )

    assert error.value.message.startswith(test_case.expected_message_prefix)
    assert error.value.code == test_case.expected_code


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
