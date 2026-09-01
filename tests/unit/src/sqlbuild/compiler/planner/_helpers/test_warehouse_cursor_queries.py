from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.planner._helpers.warehouse import snapshot as snapshot_module
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import (
    _build_cursor_queries,
    _CursorModelInfo,
    _execute_cursor_queries,
    _PhysicalCursorQuery,
    _UpstreamCursorInfo,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    CursorFetchFailureTestCase,
    CursorQueryFailureTestCase,
    CursorQueryGroupingTestCase,
    CursorQueryShapeTestCase,
)


class _RowsResult:
    def __init__(
        self,
        *,
        rows: list[tuple[str | None, ...]],
        progress: list[str],
        expected_progress_at_fetch: tuple[str, ...],
    ) -> None:
        self._rows: list[tuple[str | None, ...]] = rows
        self._progress: list[str] = progress
        self._expected_progress_at_fetch: tuple[str, ...] = expected_progress_at_fetch

    def fetchall(self) -> list[tuple[str | None, ...]]:
        assert tuple(self._progress) == self._expected_progress_at_fetch
        return self._rows


class _FailingRowsResult:
    def __init__(self, *, progress: list[str], expected_progress_at_fetch: tuple[str, ...]) -> None:
        self._progress: list[str] = progress
        self._expected_progress_at_fetch: tuple[str, ...] = expected_progress_at_fetch

    def fetchall(self) -> list[tuple[str | None, ...]]:
        assert tuple(self._progress) == self._expected_progress_at_fetch
        raise RuntimeError("result transfer failed")


class _FailFirstExecute:
    def __init__(self, *, progress: list[str]) -> None:
        self.progress: list[str] = progress
        self.sql: list[str] = []

    def __call__(self, *, connection: Any, sql: str) -> _RowsResult:
        self.sql.append(sql)
        if "schema.bad" in sql:
            assert self.progress[-1] == "Inspecting cursor bounds (1/2): schema.bad.ts [max]..."
            raise RuntimeError("warehouse unavailable")
        assert self.progress[-1] == "Inspecting cursor bounds (2/2): schema.good.ts [min,max]..."
        return _RowsResult(
            rows=[("2024-01-01", "2024-02-01")],
            progress=self.progress,
            expected_progress_at_fetch=tuple(self.progress),
        )


class _FailFirstFetch:
    def __init__(self, *, progress: list[str]) -> None:
        self.progress: list[str] = progress
        self.sql: list[str] = []

    def __call__(self, *, connection: Any, sql: str) -> _RowsResult | _FailingRowsResult:
        self.sql.append(sql)
        if "schema.bad" in sql:
            return _FailingRowsResult(
                progress=self.progress,
                expected_progress_at_fetch=(
                    "Inspecting cursor bounds (1/2): schema.bad.ts [max]...",
                ),
            )
        return _RowsResult(
            rows=[("2024-01-01", "2024-02-01")],
            progress=self.progress,
            expected_progress_at_fetch=(
                "Inspecting cursor bounds (1/2): schema.bad.ts [max]...",
                "Failed cursor bounds (1/2): schema.bad.ts [max] (0.25s): result transfer failed",
                "Inspecting cursor bounds (2/2): schema.good.ts [min,max]...",
            ),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CursorQueryGroupingTestCase(
            description="deduplicates physical reads and fans out logical tags in stable order",
            expected_physical_queries=(
                (
                    "analytics.first_target",
                    "event_time",
                    (),
                    ("first__target__max",),
                ),
                (
                    "raw.events",
                    "event_time",
                    ("first__events__min", "second__events__min"),
                    ("first__events__max", "second__events__max"),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_logical_requests_when_building_queries_then_groups_by_physical_relation(
    test_case: CursorQueryGroupingTestCase,
) -> None:
    shared_first: _UpstreamCursorInfo = _UpstreamCursorInfo(
        tag_min="first__events__min",
        tag_max="first__events__max",
        relation="raw.events",
        cursor_column="event_time",
    )
    first: _CursorModelInfo = _CursorModelInfo(
        model_name="first",
        target_tag="first__target__max",
        target_relation="analytics.first_target",
        cursor_column="event_time",
        upstreams=(shared_first, shared_first),
    )
    second: _CursorModelInfo = _CursorModelInfo(
        model_name="second",
        target_tag=None,
        target_relation=None,
        cursor_column="event_time",
        upstreams=(
            _UpstreamCursorInfo(
                tag_min="second__events__min",
                tag_max="second__events__max",
                relation="raw.events",
                cursor_column="event_time",
            ),
        ),
    )

    queries: list[_PhysicalCursorQuery] = _build_cursor_queries([first, first, second])

    actual: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = tuple(
        (query.relation, query.cursor_column, query.min_tags, query.max_tags) for query in queries
    )
    assert actual == test_case.expected_physical_queries


@pytest.mark.parametrize(
    "test_case",
    [
        CursorQueryShapeTestCase(
            description="min only",
            min_tags=("model__source__min",),
            max_tags=(),
            row=("2024-01-01",),
            expected_sql="SELECT CAST(MIN(event_time) AS VARCHAR) AS _min FROM raw.events",
            expected_results={"model__source__min": "2024-01-01"},
            expected_bounds="min",
        ),
        CursorQueryShapeTestCase(
            description="max only",
            min_tags=(),
            max_tags=("model__target__max",),
            row=("2024-02-01",),
            expected_sql="SELECT CAST(MAX(event_time) AS VARCHAR) AS _max FROM raw.events",
            expected_results={"model__target__max": "2024-02-01"},
            expected_bounds="max",
        ),
        CursorQueryShapeTestCase(
            description="min and max",
            min_tags=("first__source__min", "second__source__min"),
            max_tags=("first__source__max", "second__source__max"),
            row=("2024-01-01", "2024-02-01"),
            expected_sql=(
                "SELECT CAST(MIN(event_time) AS VARCHAR) AS _min, "
                "CAST(MAX(event_time) AS VARCHAR) AS _max FROM raw.events"
            ),
            expected_results={
                "first__source__min": "2024-01-01",
                "second__source__min": "2024-01-01",
                "first__source__max": "2024-02-01",
                "second__source__max": "2024-02-01",
            },
            expected_bounds="min,max",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_requested_bounds_when_executing_then_uses_one_standalone_query_with_observability(
    test_case: CursorQueryShapeTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress: list[str] = []
    statements: list[str] = []

    def _execute(*, connection: Any, sql: str) -> _RowsResult:
        assert progress == [
            f"Inspecting cursor bounds (1/1): raw.events.event_time [{test_case.expected_bounds}]..."
        ]
        statements.append(sql)
        return _RowsResult(
            rows=[test_case.row],
            progress=progress,
            expected_progress_at_fetch=(
                f"Inspecting cursor bounds (1/1): raw.events.event_time "
                f"[{test_case.expected_bounds}]...",
            ),
        )

    monotonic_values: Any = iter((10.0, 10.42))
    monkeypatch.setattr(snapshot_module.time, "monotonic", monotonic_values.__next__)
    query: _PhysicalCursorQuery = _PhysicalCursorQuery(
        relation="raw.events",
        cursor_column="event_time",
        min_tags=test_case.min_tags,
        max_tags=test_case.max_tags,
    )

    results: dict[str, str] = _execute_cursor_queries(
        queries=[query],
        connection=object(),
        execute=_execute,
        on_progress=progress.append,
    )

    assert results == test_case.expected_results
    assert statements == [test_case.expected_sql]
    assert "UNION ALL" not in statements[0]
    assert progress[-1] == (
        f"Inspected cursor bounds (1/1): raw.events.event_time "
        f"[{test_case.expected_bounds}] (0.42s)"
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CursorQueryFailureTestCase(
            description="failed relation remains unavailable and later relation succeeds",
            expected_results={"good__min": "2024-01-01", "good__max": "2024-02-01"},
            expected_failure_progress=(
                "Failed cursor bounds (1/2): schema.bad.ts [max] (0.25s): warehouse unavailable"
            ),
            expected_success_progress=(
                "Inspected cursor bounds (2/2): schema.good.ts [min,max] (0.50s)"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_one_failed_physical_read_when_executing_then_reports_failure_and_continues(
    test_case: CursorQueryFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress: list[str] = []
    execute: _FailFirstExecute = _FailFirstExecute(progress=progress)
    monotonic_values: Any = iter((20.0, 20.25, 30.0, 30.50))
    monkeypatch.setattr(snapshot_module.time, "monotonic", monotonic_values.__next__)
    queries: list[_PhysicalCursorQuery] = [
        _PhysicalCursorQuery(
            relation="schema.bad",
            cursor_column="ts",
            min_tags=(),
            max_tags=("bad__max",),
        ),
        _PhysicalCursorQuery(
            relation="schema.good",
            cursor_column="ts",
            min_tags=("good__min",),
            max_tags=("good__max",),
        ),
    ]

    results: dict[str, str] = _execute_cursor_queries(
        queries=queries,
        connection=object(),
        execute=execute,
        on_progress=progress.append,
    )

    assert results == test_case.expected_results
    assert len(execute.sql) == 2
    assert progress[1] == test_case.expected_failure_progress
    assert progress[3] == test_case.expected_success_progress


@pytest.mark.parametrize(
    "test_case",
    [
        CursorFetchFailureTestCase(
            description="fetch failure remains unavailable and later relation succeeds",
            expected_results={"good__min": "2024-01-01", "good__max": "2024-02-01"},
            expected_progress=(
                "Inspecting cursor bounds (1/2): schema.bad.ts [max]...",
                "Failed cursor bounds (1/2): schema.bad.ts [max] (0.25s): result transfer failed",
                "Inspecting cursor bounds (2/2): schema.good.ts [min,max]...",
                "Inspected cursor bounds (2/2): schema.good.ts [min,max] (0.50s)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fetch_failure_when_executing_then_reports_failure_and_continues(
    test_case: CursorFetchFailureTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress: list[str] = []
    execute: _FailFirstFetch = _FailFirstFetch(progress=progress)
    monotonic_values: Any = iter((20.0, 20.25, 30.0, 30.50))
    monkeypatch.setattr(snapshot_module.time, "monotonic", monotonic_values.__next__)
    queries: list[_PhysicalCursorQuery] = [
        _PhysicalCursorQuery(
            relation="schema.bad",
            cursor_column="ts",
            min_tags=(),
            max_tags=("bad__max",),
        ),
        _PhysicalCursorQuery(
            relation="schema.good",
            cursor_column="ts",
            min_tags=("good__min",),
            max_tags=("good__max",),
        ),
    ]

    results: dict[str, str] = _execute_cursor_queries(
        queries=queries,
        connection=object(),
        execute=execute,
        on_progress=progress.append,
    )

    assert results == test_case.expected_results
    assert len(execute.sql) == 2
    assert tuple(progress) == test_case.expected_progress


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
