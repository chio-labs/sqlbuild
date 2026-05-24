"""Unit tests for build source-load node execution helper."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.helpers.source_node import execute_build_source_node
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.shared.types import ExecutionResourceKind
from tests.unit.src.sqlbuild.executor.build.helpers._test_types import (
    BuildSourceNodeExecutionTestCase,
)
from tests.unit.src.sqlbuild.executor.build.helpers.helpers import (
    build_discovered_source_loader,
    build_source_load_plan_output,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSourceNodeExecutionTestCase(
            description="executes source load and records callbacks",
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            expected_progress_event="source: raw_orders",
            expected_start_event=("raw_orders", ExecutionResourceKind.SOURCE),
            expected_status=ExecutionStatus.SUCCESS,
            expected_rows=((1, "loaded"),),
        )
    ],
    ids=["executes source load and records callbacks"],
)
def test_given_build_source_node_when_executing_then_runs_loader_runtime(
    test_case: BuildSourceNodeExecutionTestCase,
    tmp_path: Path,
) -> None:
    progress_events: list[str] = []
    start_events: list[tuple[str, ExecutionResourceKind]] = []
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "source_node.duckdb")})
    plan: PlanOutput = build_source_load_plan_output(
        source_name=test_case.source_name,
        loader_name=test_case.loader_name,
    )
    try:
        result: LoadExecutionResult = execute_build_source_node(
            key=CompiledObjectKey(CompiledResourceType.SOURCE, test_case.source_name),
            plan=plan,
            loader_functions_by_name={
                test_case.loader_name: build_discovered_source_loader(
                    loader_name=test_case.loader_name
                )
            },
            loader_ref_entries={},
            adapter=adapter,
            connection_config={"database": str(tmp_path / "source_node.duckdb")},
            connection=connection,
            run_id="run-1",
            environment="dev",
            effective_vars={"region": "west"},
            is_reload=False,
            start_cursor_ts=None,
            end_cursor_ts=None,
            start_cursor_int=None,
            end_cursor_int=None,
            on_progress=progress_events.append,
            on_node_start=lambda name, kind: start_events.append((name, kind)),
        )
        rows: tuple[tuple[object, ...], ...] = tuple(
            connection.execute("SELECT id, status FROM raw_orders ORDER BY id").fetchall()
        )
    finally:
        adapter.close(connection)

    assert result.status == test_case.expected_status
    assert result.rows_loaded == len(test_case.expected_rows)
    assert result.duration_ms is not None
    assert rows == test_case.expected_rows
    assert progress_events == [test_case.expected_progress_event]
    assert start_events == [test_case.expected_start_event]
