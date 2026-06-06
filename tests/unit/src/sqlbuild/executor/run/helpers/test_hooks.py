from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.models import HookContext
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    ExecuteHooksTestCase,
    PythonHookContextParameterTestCase,
    PythonHookExecutionTestCase,
    PythonHookInvocationTestCase,
    PythonHookRuntimeErrorTestCase,
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
        phase=HookPhase.POST_HOOKS,
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
        phase=HookPhase.PRE_HOOKS,
    )

    rows: list[tuple[int]] = connection.execute("SELECT * FROM hook_log ORDER BY 1").fetchall()
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookExecutionTestCase(
            description="fails clearly when runtime hook registry is missing entry",
            hooks=[PythonHookEntry(name="notify", kwargs={"message": "done"})],
            expected_error_fragment=(
                r"post_hooks\[0\] python\(\"notify\"\) was not found in the runtime hook registry"
            ),
        )
    ],
    ids=["fails clearly when runtime hook registry is missing entry"],
)
def test_given_python_hook_without_runtime_registry_when_executing_then_it_fails_clearly(
    test_case: PythonHookExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        execute_hooks(
            connection=connection,
            adapter=adapter,
            hooks=test_case.hooks,
            phase=HookPhase.POST_HOOKS,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookInvocationTestCase(
            description="invokes function with context and kwargs",
            expected_message="done",
            expected_rows=[(1,)],
            expected_model_name="orders",
            expected_phase="post_hooks",
            expected_hook_name="notify",
            expected_hook_index=0,
            expected_run_id="run-1",
            expected_environment="dev",
            expected_vars={"channel": "alerts"},
            expected_destination_name="orders",
            expected_destination_schema="main",
            expected_adapter_name="duckdb",
            expected_recorded_events=(
                "CREATE TABLE hook_log AS SELECT 1 AS value",
                "SELECT value FROM hook_log",
                "done",
            ),
        )
    ],
    ids=["invokes function with context and kwargs"],
)
def test_given_python_hook_when_executing_then_invokes_function_with_context_and_kwargs(
    test_case: PythonHookInvocationTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    statement_recorder: StatementRecorder = StatementRecorder()
    captured: list[tuple[HookContext, str, list[tuple[object, ...]]]] = []

    def notify(ctx: HookContext, message: str) -> None:
        ctx.execute_sql("CREATE TABLE hook_log AS SELECT 1 AS value")
        rows: list[tuple[object, ...]] = ctx.query("SELECT value FROM hook_log")
        ctx.log(message)
        captured.append((ctx, message, rows))

    execute_hooks(
        connection=connection,
        adapter=adapter,
        hooks=[PythonHookEntry(name="notify", kwargs={"message": "done"})],
        phase=HookPhase.POST_HOOKS,
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/notifications.py"),
                name="notify",
                function=notify,
            ),
        ),
        model_name="orders",
        destination=CompiledRelationDestination(
            database=None,
            schema="main",
            name="orders",
            qualified_name=None,
        ),
        run_id="run-1",
        environment="dev",
        effective_vars={"channel": "alerts"},
        statement_recorder=statement_recorder,
    )

    ctx, message, rows = captured[0]
    assert message == test_case.expected_message
    assert rows == test_case.expected_rows
    assert ctx.model_name == test_case.expected_model_name
    assert ctx.phase == test_case.expected_phase
    assert ctx.hook_name == test_case.expected_hook_name
    assert ctx.hook_index == test_case.expected_hook_index
    assert ctx.run_id == test_case.expected_run_id
    assert ctx.environment == test_case.expected_environment
    assert ctx.vars == test_case.expected_vars
    assert ctx.destination.name == test_case.expected_destination_name
    assert ctx.destination.schema == test_case.expected_destination_schema
    assert ctx.adapter_name == test_case.expected_adapter_name
    assert tuple(event.content for event in statement_recorder.snapshot()) == (
        test_case.expected_recorded_events
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookContextParameterTestCase(
            description="injects context parameter aliases and ignores return values",
            hook_name="aliases",
            expected_context_count=3,
            expected_return_ignored=None,
        )
    ],
    ids=["injects context parameter aliases and ignores return values"],
)
def test_given_python_hooks_when_executing_then_injects_supported_context_aliases(
    test_case: PythonHookContextParameterTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    captured_contexts: list[HookContext] = []

    def uses_ctx(ctx: HookContext) -> object:
        captured_contexts.append(ctx)
        return test_case.expected_return_ignored

    def uses_context(context: HookContext) -> object:
        captured_contexts.append(context)
        return test_case.expected_return_ignored

    def uses_hook_context(hook_context: HookContext) -> object:
        captured_contexts.append(hook_context)
        return test_case.expected_return_ignored

    execute_hooks(
        connection=connection,
        adapter=adapter,
        hooks=[
            PythonHookEntry(name="uses_ctx", kwargs={}),
            PythonHookEntry(name="uses_context", kwargs={}),
            PythonHookEntry(name="uses_hook_context", kwargs={}),
        ],
        phase=HookPhase.PRE_HOOKS,
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/aliases.py"),
                name="uses_ctx",
                function=uses_ctx,
            ),
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/aliases.py"),
                name="uses_context",
                function=uses_context,
            ),
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/aliases.py"),
                name="uses_hook_context",
                function=uses_hook_context,
            ),
        ),
        model_name="orders",
        destination=CompiledRelationDestination(
            database=None,
            schema="main",
            name="orders",
            qualified_name=None,
        ),
        run_id="run-1",
    )

    assert len(captured_contexts) == test_case.expected_context_count
    assert tuple(ctx.hook_index for ctx in captured_contexts) == (0, 1, 2)
    assert all(ctx.phase == HookPhase.PRE_HOOKS for ctx in captured_contexts)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonHookRuntimeErrorTestCase(
            description="wraps Python hook exceptions with hook label",
            expected_error_fragment=r"post_hooks\[0\] python\(\"explode\"\) failed: boom",
        )
    ],
    ids=["wraps Python hook exceptions with hook label"],
)
def test_given_python_hook_raises_when_executing_then_reports_hook_label(
    test_case: PythonHookRuntimeErrorTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    def explode(ctx: HookContext) -> None:
        raise RuntimeError("boom")

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        execute_hooks(
            connection=connection,
            adapter=adapter,
            hooks=[PythonHookEntry(name="explode", kwargs={})],
            phase=HookPhase.POST_HOOKS,
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/explode.py"),
                    name="explode",
                    function=explode,
                ),
            ),
            model_name="orders",
            destination=CompiledRelationDestination(
                database=None,
                schema="main",
                name="orders",
                qualified_name=None,
            ),
            run_id="run-1",
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
            phase=HookPhase.POST_HOOKS,
        )
