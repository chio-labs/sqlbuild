"""Tests for source loader cursor helpers."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from sqlbuild.adapter.contract.types import CursorKind
from sqlbuild.executor.load._helpers.cursors import infer_cursor_kind
from tests.unit.src.sqlbuild.executor.load._test_types import LoaderCursorKindTestCase


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
