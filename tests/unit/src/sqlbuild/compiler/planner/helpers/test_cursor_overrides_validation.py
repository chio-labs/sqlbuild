"""Tests for CursorOverrides CLI flag validation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.models import CursorOverrides
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    CursorOverridesValidationTestCase,
)

VALID_TEST_CASES: list[CursorOverridesValidationTestCase] = [
    CursorOverridesValidationTestCase(
        description="valid ISO date for timestamp",
        start_ts="2024-01-01",
        end_ts="2024-02-01T12:00:00",
        expected_valid=True,
    ),
    CursorOverridesValidationTestCase(
        description="valid integer values",
        start_int="1000",
        end_int="2000",
        expected_valid=True,
    ),
    CursorOverridesValidationTestCase(
        description="all none passes",
        expected_valid=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    VALID_TEST_CASES,
    ids=[case.description for case in VALID_TEST_CASES],
)
def test_given_valid_cursor_overrides_when_constructing_then_passes(
    test_case: CursorOverridesValidationTestCase,
) -> None:
    CursorOverrides(
        start_ts=test_case.start_ts,
        end_ts=test_case.end_ts,
        start_int=test_case.start_int,
        end_int=test_case.end_int,
    )

    assert test_case.expected_valid


ERROR_TEST_CASES: list[CursorOverridesValidationTestCase] = [
    CursorOverridesValidationTestCase(
        description="invalid timestamp raises",
        start_ts="not-a-date",
        expected_valid=False,
        expected_error_fragment="not a valid ISO timestamp",
    ),
    CursorOverridesValidationTestCase(
        description="non-numeric integer raises",
        start_int="abc",
        expected_valid=False,
        expected_error_fragment="not a valid integer",
    ),
    CursorOverridesValidationTestCase(
        description="float integer raises",
        start_int="3.14",
        expected_valid=False,
        expected_error_fragment="not a whole number",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_cursor_overrides_when_constructing_then_raises(
    test_case: CursorOverridesValidationTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment or ""):
        CursorOverrides(
            start_ts=test_case.start_ts,
            end_ts=test_case.end_ts,
            start_int=test_case.start_int,
            end_int=test_case.end_int,
        )
