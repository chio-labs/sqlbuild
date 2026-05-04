from __future__ import annotations

import pytest

from sqlbuild.integrations.databricks.client import DatabricksAdapter
from tests.unit.src.sqlbuild.integrations.databricks._test_types import (
    DatabricksRenderDeleteInsertCursorTestCase,
)

TEST_CASES: list[DatabricksRenderDeleteInsertCursorTestCase] = [
    DatabricksRenderDeleteInsertCursorTestCase(
        description="renders replace where for timestamp cursor bounds",
        target="`workspace`.`test`.`orders`",
        sql="SELECT * FROM `workspace`.`test`.`orders__delta`",
        cursor_column="ordered_at",
        cursor_start="2026-01-01 00:00:00",
        cursor_end="2026-01-02 00:00:00",
        columns=None,
        expected_statements=(
            "INSERT INTO `workspace`.`test`.`orders` REPLACE WHERE "
            "ordered_at >= TIMESTAMP '2026-01-01 00:00:00' AND "
            "ordered_at < TIMESTAMP '2026-01-02 00:00:00' "
            "SELECT * FROM `workspace`.`test`.`orders__delta`",
        ),
    ),
    DatabricksRenderDeleteInsertCursorTestCase(
        description="renders replace where with explicit columns",
        target="`workspace`.`test`.`orders`",
        sql="SELECT id, status FROM `workspace`.`test`.`orders__delta`",
        cursor_column="id",
        cursor_start="1",
        cursor_end="10",
        columns=("id", "status"),
        expected_statements=(
            "INSERT INTO `workspace`.`test`.`orders` (id, status) REPLACE WHERE "
            "id >= 1 AND id < 10 "
            "SELECT id, status FROM `workspace`.`test`.`orders__delta`",
        ),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_cursor_delete_insert_when_rendering_then_databricks_uses_replace_where(
    test_case: DatabricksRenderDeleteInsertCursorTestCase,
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()

    statements: tuple[str, ...] = adapter.render_delete_insert_cursor(
        target=test_case.target,
        sql=test_case.sql,
        cursor_column=test_case.cursor_column,
        cursor_start=test_case.cursor_start,
        cursor_end=test_case.cursor_end,
        columns=test_case.columns,
    )

    assert statements == test_case.expected_statements
