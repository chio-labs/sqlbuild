from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import CursorValue
from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.integrations.duckdb.helpers._test_types import (
    BuildAttachSqlTestCase,
    BuildCursorFilterTestCase,
)

BUILD_ATTACH_SQL_TEST_CASES: list[BuildAttachSqlTestCase] = [
    BuildAttachSqlTestCase(
        description="attaches database with path only",
        attach_entry={"path": "/tmp/other.duckdb"},
        expected_sql="ATTACH '/tmp/other.duckdb'",
    ),
    BuildAttachSqlTestCase(
        description="attaches database with alias",
        attach_entry={"path": "/tmp/other.duckdb", "alias": "other"},
        expected_sql="ATTACH '/tmp/other.duckdb' AS other",
    ),
    BuildAttachSqlTestCase(
        description="attaches database with type and read_only",
        attach_entry={
            "path": "sqlite.db",
            "alias": "sqlite_db",
            "type": "sqlite",
            "read_only": True,
        },
        expected_sql="ATTACH 'sqlite.db' AS sqlite_db (TYPE sqlite, READ_ONLY)",
    ),
    BuildAttachSqlTestCase(
        description="attaches database with read_only false omits option",
        attach_entry={"path": "/tmp/data.duckdb", "read_only": False},
        expected_sql="ATTACH '/tmp/data.duckdb'",
    ),
    BuildAttachSqlTestCase(
        description="attaches database with type only",
        attach_entry={"path": "pg.db", "type": "postgres"},
        expected_sql="ATTACH 'pg.db' (TYPE postgres)",
    ),
]

BUILD_CURSOR_FILTER_TEST_CASES: list[BuildCursorFilterTestCase] = [
    BuildCursorFilterTestCase(
        description="returns empty when cursor column is none",
        cursor_column=None,
        start_cursor=None,
        end_cursor=None,
        expected_filter="",
    ),
    BuildCursorFilterTestCase(
        description="returns empty when start cursor is none",
        cursor_column="event_time",
        start_cursor=None,
        end_cursor=None,
        expected_filter="",
    ),
    BuildCursorFilterTestCase(
        description="returns start bound only when end cursor is none",
        cursor_column="event_time",
        start_cursor=CursorValue(kind=CursorKind.INTEGER, value=100),
        end_cursor=None,
        expected_filter="event_time >= '100'",
    ),
    BuildCursorFilterTestCase(
        description="returns both bounds when start and end cursors are set",
        cursor_column="id",
        start_cursor=CursorValue(kind=CursorKind.INTEGER, value=10),
        end_cursor=CursorValue(kind=CursorKind.INTEGER, value=20),
        expected_filter="id >= '10' AND id < '20'",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_ATTACH_SQL_TEST_CASES,
    ids=[case.description for case in BUILD_ATTACH_SQL_TEST_CASES],
)
def test_given_attach_entry_when_building_sql_then_returns_expected_statement(
    test_case: BuildAttachSqlTestCase,
) -> None:
    result: str = DuckDbAdapter().duckdb_build_attach_sql(test_case.attach_entry)

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    BUILD_CURSOR_FILTER_TEST_CASES,
    ids=[case.description for case in BUILD_CURSOR_FILTER_TEST_CASES],
)
def test_given_cursor_params_when_building_filter_then_returns_expected_clause(
    test_case: BuildCursorFilterTestCase,
) -> None:
    result: str = DuckDbAdapter().build_cursor_filter(
        cursor_column=test_case.cursor_column,
        start_cursor=test_case.start_cursor,
        end_cursor=test_case.end_cursor,
    )

    assert result == test_case.expected_filter
