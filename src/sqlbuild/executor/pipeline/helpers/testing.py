"""Test execution pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import FunctionInfo, StatementRecorder
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.models import FunctionPlanEntry, PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.build.models import FunctionExecutionResult
from sqlbuild.executor.functions.main.execute import execute_function
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.constants import SQL_TEST_EXECUTION_ERROR_CODE
from sqlbuild.executor.testing.main.execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.shared.types import ConnectionElapsedCallback


def run_test_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_test_start: Callable[[SqlTestPlanEntry], None] | None = None,
    on_test_complete: Callable[[SqlTestExecutionResult], None] | None = None,
) -> tuple[SqlTestExecutionResult, ...]:
    """Execute all SQL unit tests from a compiled plan."""

    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, elapsed_seconds=time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, elapsed_seconds=time.monotonic() - start)
    try:
        preflight_start: float = time.monotonic()
        if on_progress is not None:
            on_progress("Preparing test functions...")
        missing_functions_by_test: dict[str, tuple[str, ...]] = _prepare_test_functions(
            plan=plan,
            adapter=adapter,
            connection=connection,
        )
        if on_progress is not None:
            on_progress(f"Prepared test functions. ({time.monotonic() - preflight_start:.2f}s)")
        results: list[SqlTestExecutionResult] = []
        entry: SqlTestPlanEntry
        for entry in plan.test_entries:
            if on_test_start is not None:
                on_test_start(entry)
            missing_functions: tuple[str, ...] = missing_functions_by_test.get(entry.name, ())
            if missing_functions:
                result: SqlTestExecutionResult = _build_missing_function_result(
                    test_entry=entry,
                    missing_functions=missing_functions,
                )
                results.append(result)
                if on_test_complete is not None:
                    on_test_complete(result)
                continue
            result: SqlTestExecutionResult = execute_sql_test(
                test_entry=entry, adapter=adapter, connection=connection
            )
            results.append(result)
            if on_test_complete is not None:
                on_test_complete(result)
        return tuple(results)
    finally:
        adapter.close(connection)


def _prepare_test_functions(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
) -> dict[str, tuple[str, ...]]:
    function_entries: dict[CompiledObjectKey, FunctionPlanEntry] = {
        entry.key: entry for entry in plan.function_entries
    }
    required_targets_by_key: dict[CompiledObjectKey, CompiledRelationLocation] = {}
    test_entry: SqlTestPlanEntry
    for test_entry in plan.test_entries:
        dep: CompiledObjectKey
        for dep in test_entry.function_deps:
            function_target: CompiledRelationLocation | None = plan.function_locations.get(dep.name)
            if function_target is not None:
                required_targets_by_key[dep] = function_target
    if not required_targets_by_key:
        return {}

    existing_function_names: set[tuple[str | None, str | None, str]] = set()
    for database, schema, names in _group_function_names(required_targets_by_key.values()):
        function_infos: tuple[FunctionInfo, ...] = adapter.list_functions(
            connection,
            database=database,
            schemas=(schema,) if schema is not None else None,
            names=names,
        )
        existing_function_names.update(
            (
                _normalize_name(info.database),
                _normalize_name(info.schema),
                _normalize_required_name(info.name),
            )
            for info in function_infos
        )

    missing_by_key: dict[CompiledObjectKey, str] = {}
    key: CompiledObjectKey
    target: CompiledRelationLocation
    for key, target in required_targets_by_key.items():
        function_key: tuple[str | None, str | None, str] = (
            _normalize_name(target.database),
            _normalize_name(target.schema),
            _normalize_required_name(target.name),
        )
        if function_key not in existing_function_names:
            missing_by_key[key] = key.name

    _register_connection_scoped_python_functions(
        missing_by_key=missing_by_key,
        function_entries=function_entries,
        adapter=adapter,
        connection=connection,
    )

    missing_by_test: dict[str, tuple[str, ...]] = {}
    for test_entry in plan.test_entries:
        missing_names: tuple[str, ...] = tuple(
            missing_by_key[dep] for dep in test_entry.function_deps if dep in missing_by_key
        )
        if missing_names:
            missing_by_test[test_entry.name] = missing_names
    return missing_by_test


def _register_connection_scoped_python_functions(
    *,
    missing_by_key: dict[CompiledObjectKey, str],
    function_entries: dict[CompiledObjectKey, FunctionPlanEntry],
    adapter: BaseAdapter,
    connection: Any,
) -> None:
    if adapter.persists_python_functions():
        return
    key: CompiledObjectKey
    for key in tuple(missing_by_key):
        function_entry: FunctionPlanEntry | None = function_entries.get(key)
        if function_entry is None or function_entry.language != FunctionLanguage.PYTHON:
            continue
        result: FunctionExecutionResult = execute_function(
            function_entry=function_entry,
            adapter=adapter,
            connection=connection,
            statement_recorder=StatementRecorder(),
            run_id="test",
            query_change_tracking=False,
        )
        if result.status == ExecutionStatus.SUCCESS:
            del missing_by_key[key]


def _group_function_names(
    targets: Iterable[CompiledRelationLocation],
) -> tuple[tuple[str | None, str | None, tuple[str, ...]], ...]:
    grouped: dict[tuple[str | None, str | None], list[str]] = {}
    target: CompiledRelationLocation
    for target in targets:
        grouped.setdefault((target.database, target.schema), []).append(target.name)
    return tuple((database, schema, tuple(names)) for (database, schema), names in grouped.items())


def _normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    return value.lower()


def _normalize_required_name(value: str) -> str:
    return value.lower()


def _build_missing_function_result(
    *,
    test_entry: SqlTestPlanEntry,
    missing_functions: tuple[str, ...],
) -> SqlTestExecutionResult:
    function_list: str = ", ".join(missing_functions)
    error_message: str = (
        f"test '{test_entry.name}' depends on project function(s) {function_list}, "
        "but they do not exist in the target database. Run `sqb build` first, "
        "or build the required function(s) before running `sqb test`."
    )
    model_name: str = test_entry.chain[0].model_name if test_entry.chain else test_entry.name
    return SqlTestExecutionResult(
        test_name=test_entry.name,
        outcome=SqlTestOutcome.ERROR,
        step_results=(
            StepResult(
                model_name=model_name,
                outcome=SqlTestOutcome.ERROR,
                error_code=SQL_TEST_EXECUTION_ERROR_CODE,
                error_message=error_message,
            ),
        ),
        error_code=SQL_TEST_EXECUTION_ERROR_CODE,
        error_message=error_message,
    )
