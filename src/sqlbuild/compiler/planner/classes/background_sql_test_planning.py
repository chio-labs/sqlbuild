"""Plan SQL tests on a worker thread while the planner waits on the warehouse."""

from __future__ import annotations

import threading
from concurrent.futures import Future
from types import TracebackType

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.output.plan_output import plan_selected_sql_tests
from sqlbuild.compiler.planner.models import PlannedSqlTests, SqlTestSelection


class BackgroundSqlTestPlanning:
    """Start warehouse-independent SQL test planning early and join it before assembly."""

    def __init__(
        self,
        *,
        project: CompiledProject,
        adapter: BaseAdapter,
        selected_keys: frozenset[CompiledObjectKey],
        sql_test_selection: SqlTestSelection,
        enabled: bool,
    ) -> None:
        self._future: Future[PlannedSqlTests] | None = None
        if enabled:
            future: Future[PlannedSqlTests] = Future()
            self._future = future
            threading.Thread(
                target=_plan_into,
                kwargs={
                    "future": future,
                    "project": project,
                    "adapter": adapter,
                    "selected_keys": selected_keys,
                    "sql_test_selection": sql_test_selection,
                },
                name="sqlbuild-test-planning",
                daemon=True,
            ).start()
        self._selected_keys: frozenset[CompiledObjectKey] = selected_keys
        self._sql_test_selection: SqlTestSelection = sql_test_selection

    def __enter__(self) -> BackgroundSqlTestPlanning:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback

    def result(self) -> PlannedSqlTests:
        """Return planned tests, raising any planning error at the original assembly point."""

        if self._future is None:
            return PlannedSqlTests(
                selected_keys=self._selected_keys, sql_test_selection=self._sql_test_selection
            )
        return self._future.result()


def _plan_into(
    *,
    future: Future[PlannedSqlTests],
    project: CompiledProject,
    adapter: BaseAdapter,
    selected_keys: frozenset[CompiledObjectKey],
    sql_test_selection: SqlTestSelection,
) -> None:
    """Run planning on a daemon thread so a failed plan never waits for it at exit."""

    try:
        future.set_result(
            plan_selected_sql_tests(
                project=project,
                adapter=adapter,
                selected_keys=selected_keys,
                sql_test_selection=sql_test_selection,
            )
        )
    except BaseException as error:  # noqa: BLE001 - re-raised on the joining thread
        future.set_exception(error)
