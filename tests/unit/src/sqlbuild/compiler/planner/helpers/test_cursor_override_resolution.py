"""Tests for typed cursor override resolution per model."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.planner.helpers.output.plan_entry import resolve_cursor_overrides
from sqlbuild.compiler.planner.models import CursorOverrides
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    CursorOverrideResolutionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_cursor_override_model,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorOverrideResolutionTestCase(
            description="timestamp model picks start_ts override",
            cursor_type="timestamp",
            start_ts="2024-01-01",
            end_ts="2024-02-01",
            start_int=None,
            end_int=None,
            generic_start=None,
            generic_end=None,
            expected_start="2024-01-01",
            expected_end="2024-02-01",
        ),
        CursorOverrideResolutionTestCase(
            description="integer model picks start_int override",
            cursor_type="integer",
            start_ts=None,
            end_ts=None,
            start_int="1000",
            end_int="2000",
            generic_start=None,
            generic_end=None,
            expected_start="1000",
            expected_end="2000",
        ),
        CursorOverrideResolutionTestCase(
            description="timestamp model ignores integer overrides",
            cursor_type="timestamp",
            start_ts=None,
            end_ts=None,
            start_int="1000",
            end_int="2000",
            generic_start=None,
            generic_end=None,
            expected_start=None,
            expected_end=None,
        ),
        CursorOverrideResolutionTestCase(
            description="no cursor_type falls back to generic",
            cursor_type=None,
            start_ts="2024-01-01",
            end_ts="2024-02-01",
            start_int=None,
            end_int=None,
            generic_start="fallback_start",
            generic_end="fallback_end",
            expected_start="fallback_start",
            expected_end="fallback_end",
        ),
        CursorOverrideResolutionTestCase(
            description="none cursor_overrides uses generic values",
            cursor_type="timestamp",
            start_ts=None,
            end_ts=None,
            start_int=None,
            end_int=None,
            generic_start="generic_start",
            generic_end="generic_end",
            expected_start="generic_start",
            expected_end="generic_end",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_and_overrides_when_resolving_then_returns_expected(
    test_case: CursorOverrideResolutionTestCase,
) -> None:
    model: CompiledModel = build_cursor_override_model(test_case.cursor_type)
    has_typed: bool = any(
        v is not None
        for v in (test_case.start_ts, test_case.end_ts, test_case.start_int, test_case.end_int)
    )
    overrides: CursorOverrides | None = (
        CursorOverrides(
            start_ts=test_case.start_ts,
            end_ts=test_case.end_ts,
            start_int=test_case.start_int,
            end_int=test_case.end_int,
        )
        if has_typed
        else None
    )

    start: str | None
    end: str | None
    start, end = resolve_cursor_overrides(
        model=model,
        cursor_overrides=overrides,
        start_cursor_override=test_case.generic_start,
        end_cursor_override=test_case.generic_end,
    )

    assert start == test_case.expected_start
    assert end == test_case.expected_end
