"""Tests for source loader cursor helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from sqlbuild.adapter.contract.types import CursorKind
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.load._helpers.cursors import _parse_loader_cursor, infer_cursor_kind
from tests.unit.src.sqlbuild.executor.load._test_types import (
    LoaderCursorKindTestCase,
    LoaderCursorParseErrorTestCase,
    LoaderCursorParseTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        LoaderCursorParseTestCase(
            description="integral decimal is an integer cursor",
            value=Decimal("42"),
            expected_value=IntegerValue(value=42),
            expected_rendered="42",
        ),
        LoaderCursorParseTestCase(
            description="ISO date string is a date cursor",
            value="2026-04-04",
            expected_value=DateValue(value=date(2026, 4, 4)),
            expected_rendered="2026-04-04",
        ),
        LoaderCursorParseTestCase(
            description="ISO timestamp string is a timestamp cursor",
            value="2026-04-04T14:30:00.000001",
            expected_value=TimestampValue(value=datetime(2026, 4, 4, 14, 30, 0, 1)),
            expected_rendered="2026-04-04T14:30:00.000001",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_supported_staging_cursor_when_parsing_then_returns_typed_value(
    test_case: LoaderCursorParseTestCase,
) -> None:
    result: CursorScalar | None = _parse_loader_cursor(value=test_case.value)

    assert result == test_case.expected_value
    assert result is not None
    assert render(value=result) == test_case.expected_rendered


@pytest.mark.parametrize(
    "test_case",
    (
        LoaderCursorParseErrorTestCase(
            description="non-integral decimal uses the core parse error",
            value=Decimal("42.7"),
            expected_error_type=CursorAlgebraError,
            expected_error_fragment="non-integral integer cursor value: 42.7",
        ),
        LoaderCursorParseErrorTestCase(
            description="float is rejected by the loader boundary",
            value=42.0,
            expected_error_type=ExecutorInputError,
            expected_error_fragment="do not support float",
        ),
        LoaderCursorParseErrorTestCase(
            description="boolean is rejected by the loader boundary",
            value=True,
            expected_error_type=ExecutorInputError,
            expected_error_fragment="do not support boolean values",
        ),
        LoaderCursorParseErrorTestCase(
            description="bytes are rejected by the loader boundary",
            value=b"42",
            expected_error_type=ExecutorInputError,
            expected_error_fragment="do not support bytes",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsupported_staging_cursor_when_parsing_then_fails_clearly(
    test_case: LoaderCursorParseErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        _parse_loader_cursor(value=test_case.value)


@pytest.mark.parametrize(
    "test_case",
    [
        LoaderCursorKindTestCase(
            description="infers integer from a native integer lower bound",
            value=42,
            expected_cursor_kind=CursorKind.INTEGER,
        ),
        LoaderCursorKindTestCase(
            description="does not infer integer from a boolean lower bound",
            value=True,
            expected_cursor_kind=None,
        ),
        LoaderCursorKindTestCase(
            description="infers timestamp from a native datetime lower bound",
            value=datetime(2026, 4, 4, 14, 30, 0, 1),
            expected_cursor_kind=CursorKind.TIMESTAMP,
        ),
        LoaderCursorKindTestCase(
            description="does not infer timestamp from a native date lower bound",
            value=date(2026, 4, 4),
            expected_cursor_kind=None,
        ),
        LoaderCursorKindTestCase(
            description="does not infer a kind from a string lower bound",
            value="2026-04-04T14:30:00.000001",
            expected_cursor_kind=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_staging_lower_bound_when_inferring_then_returns_semantic_cursor_kind(
    test_case: LoaderCursorKindTestCase,
) -> None:
    cursor_kind: CursorKind | None = infer_cursor_kind(test_case.value)

    assert cursor_kind == test_case.expected_cursor_kind
