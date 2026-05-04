from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.unit.src.sqlbuild.integrations.duckdb._test_types import (
    DuckDbRenderCursorBoundLiteralTestCase,
)

TEST_CASES: list[DuckDbRenderCursorBoundLiteralTestCase] = [
    DuckDbRenderCursorBoundLiteralTestCase(
        description="renders timestamp cursor bounds as typed literals",
        value="2024-01-15T00:00:00",
        cursor_type=CursorKind.TIMESTAMP,
        expected_literal="TIMESTAMP '2024-01-15T00:00:00'",
    ),
    DuckDbRenderCursorBoundLiteralTestCase(
        description="renders integer cursor bounds without quotes",
        value="42",
        cursor_type=CursorKind.INTEGER,
        expected_literal="42",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cursor_bounds_when_rendering_then_duckdb_returns_expected_literal(
    test_case: DuckDbRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    result: str = adapter.render_cursor_bound_literal(test_case.value, test_case.cursor_type)

    assert result == test_case.expected_literal
