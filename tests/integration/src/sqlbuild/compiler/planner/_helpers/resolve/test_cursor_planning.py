"""Native cursor resolution through the planner and a custom warehouse adapter."""

from datetime import datetime
from typing import Any

import pytest

from sqlbuild._native import CursorBounds, ModelPlanEntry, PlanOutput
from tests.integration.src.sqlbuild.compiler.planner._helpers.resolve._test_types import (
    CursorPlannerTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner._helpers.resolve.helpers import (
    CursorLiteralOverrideAdapter,
)
from tests.integration.src.sqlbuild.compiler.planner.main.helpers import (
    build_execution_plan_from_kwargs,
    build_future_cursor_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorPlannerTestCase(
            description="leap-day source window preserves the observed start and advances the end",
            expected_start="2024-02-28 12:00:00",
            expected_end="2024-03-01T00:00:00",
            expected_rows=[(datetime(2024, 2, 28, 12),), (datetime(2024, 2, 29, 23, 59, 59),)],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_live_source_when_planning_then_custom_cursor_literals_execute_exact_window(
    test_case: CursorPlannerTestCase,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE raw.events (occurred_at TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw.events VALUES ('2024-02-28 12:00:00'), ('2024-02-29 23:59:59')"
    )
    adapter: CursorLiteralOverrideAdapter = CursorLiteralOverrideAdapter()
    plan: PlanOutput = build_execution_plan_from_kwargs(
        project=build_future_cursor_project(), adapter=adapter, connection=connection
    )
    entry: ModelPlanEntry = plan.model_entries[0]
    assert entry.cursor_bounds == CursorBounds(
        start=test_case.expected_start, end=test_case.expected_end
    )
    assert "/* custom cursor literal */" in entry.resolved_sql
    assert (test_case.expected_start, "timestamp") in adapter.cursor_literals
    assert (test_case.expected_end, "timestamp") in adapter.cursor_literals
    assert connection.execute(entry.resolved_sql).fetchall() == test_case.expected_rows


if __name__ == "__main__":
    pytest.main([__file__])
