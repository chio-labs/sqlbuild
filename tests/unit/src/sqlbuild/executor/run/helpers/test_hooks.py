from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    ExecuteHooksTestCase,
    PythonHookExecutionTestCase,
    RenderHooksTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderHooksTestCase(
            description="renders only SQL entries from mixed typed hooks",
            hooks=[
                SqlHookEntry(statement="CREATE TABLE hook_log AS SELECT 1"),
                PythonHookEntry(name="notify", kwargs={"message": "done"}),
                SqlHookEntry(statement="INSERT INTO hook_log SELECT 2"),
            ],
            expected_statements=(
                "CREATE TABLE hook_log AS SELECT 1",
                "INSERT INTO hook_log SELECT 2",
            ),
        )
    ],
    ids=["renders only SQL entries from mixed typed hooks"],
)
def test_given_typed_hooks_when_rendering_then_returns_expected_statements(
    test_case: RenderHooksTestCase,
) -> None:
    rendered: tuple[str, ...] = render_hooks(
        hooks=test_case.hooks,
        phase_label="post_hooks",
    )

    assert rendered == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteHooksTestCase(
            description="executes typed SQL statements in order",
            hooks=[
                SqlHookEntry(statement="CREATE TABLE hook_log AS SELECT 1"),
                SqlHookEntry(statement="INSERT INTO hook_log SELECT 2"),
            ],
            expected_rows=((1,), (2,)),
        )
    ],
    ids=["executes typed SQL statements in order"],
)
def test_given_typed_sql_hooks_when_executing_then_sql_statements_run_in_order(
    test_case: ExecuteHooksTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    execute_hooks(
        connection=connection,
        adapter=adapter,
        hooks=test_case.hooks,
        phase_label="pre_hooks",
    )

    rows: list[tuple[int]] = connection.execute("SELECT * FROM hook_log ORDER BY 1").fetchall()
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookExecutionTestCase(
            description="fails clearly for Python hooks before execution support exists",
            hooks=[PythonHookEntry(name="notify", kwargs={"message": "done"})],
            expected_error_fragment=(
                r"post_hooks\[0\] python\(\"notify\"\) is valid at compile time, "
                r"but Python hook execution is not implemented yet"
            ),
        )
    ],
    ids=["fails clearly for Python hooks before execution support exists"],
)
def test_given_python_hook_when_executing_then_it_fails_until_python_hooks_exist(
    test_case: PythonHookExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        execute_hooks(
            connection=connection,
            adapter=adapter,
            hooks=test_case.hooks,
            phase_label="post_hooks",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookExecutionTestCase(
            description="fails clearly for invalid hook entry shape",
            hooks=[SqlHookEntry(statement="SELECT 1"), object()],
            expected_error_fragment=(
                r"post_hooks\[1\] must be sql\(\"\.\.\.\"\) or python\(\"\.\.\.\"\), "
                r"got object"
            ),
        )
    ],
    ids=["fails clearly for invalid hook entry shape"],
)
def test_given_invalid_hook_entry_when_executing_then_it_reports_hook_index(
    test_case: PythonHookExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        execute_hooks(
            connection=connection,
            adapter=adapter,
            hooks=test_case.hooks,
            phase_label="post_hooks",
        )
