"""Plan SQL tests on a worker thread while the planner waits on the warehouse."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from types import TracebackType

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.output.plan_output import plan_selected_sql_tests
from sqlbuild.compiler.planner.models import PlannedSqlTests


class BackgroundSqlTestPlanning:
    """Start warehouse-independent SQL test planning early and join it before assembly."""

    def __init__(
        self,
        *,
        project: CompiledProject,
        adapter: BaseAdapter,
        selected_keys: frozenset[CompiledObjectKey],
        enabled: bool,
    ) -> None:
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="sqlbuild-test-planning"
        )
        self._future: Future[PlannedSqlTests] | None = (
            self._executor.submit(
                plan_selected_sql_tests,
                project=project,
                adapter=adapter,
                selected_keys=selected_keys,
            )
            if enabled
            else None
        )
        self._selected_keys: frozenset[CompiledObjectKey] = selected_keys

    def __enter__(self) -> BackgroundSqlTestPlanning:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def result(self) -> PlannedSqlTests:
        """Return planned tests, raising any planning error at the original assembly point."""

        if self._future is None:
            return PlannedSqlTests(selected_keys=self._selected_keys)
        return self._future.result()
