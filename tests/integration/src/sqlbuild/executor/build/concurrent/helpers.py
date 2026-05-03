"""Test helpers for concurrent build execution tests."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.main import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import TablePromotionMode
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.build.concurrent._test_types import (
    ConcurrentBuildTestCase,
)


def run_concurrent_build(
    *,
    test_case: ConcurrentBuildTestCase,
    project_dir: Path,
    db_path: Path,
    adapter: DuckDbAdapter,
) -> BuildExecutionResult:
    """Run a concurrent build against a file-based DuckDB database."""

    config: dict[str, object] = {"database": str(db_path)}

    setup_connection: Any = adapter.connect(config)
    try:
        sql: str
        for sql in test_case.setup_sql:
            setup_connection.execute(sql)
    finally:
        adapter.close(setup_connection)

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered,
        adapter=adapter,
        no_sql_validation=True,
        connection_config=config,
    )
    plan: PlanOutput = pipeline_result.plan_output

    scheduler_connection: Any = adapter.connect(config)
    worker_connections: list[Any] = []
    _i: int
    for _i in range(test_case.max_concurrency):
        worker_connections.append(adapter.connect(config))
    try:
        return execute_build_plan(
            plan=plan,
            adapter=adapter,
            connections=tuple(worker_connections),
            scheduler_connection=scheduler_connection,
            promotion_mode=TablePromotionMode.STAGED,
            run_id="test_concurrent",
            query_change_tracking=True,
            run_audits=test_case.run_audits,
            fail_fast=test_case.fail_fast,
        )
    finally:
        conn: Any
        for conn in worker_connections:
            adapter.close(conn)
        adapter.close(scheduler_connection)


def build_ordering_trace_callbacks(
    *,
    completed_at_start: list[tuple[str, frozenset[str]]],
    completed_names: set[str],
    lock: threading.Lock,
) -> tuple[Any, Any]:
    """Build on_node_start/on_node_complete callbacks that record ordering traces."""

    def on_node_start(name: str, _materialization_type: str) -> None:
        with lock:
            snapshot: frozenset[str] = frozenset(completed_names)
            completed_at_start.append((name, snapshot))

    def on_node_complete(node_result: object) -> None:
        name: str | None = _extract_node_name(node_result)
        if name is not None:
            with lock:
                completed_names.add(name)

    return on_node_start, on_node_complete


def _extract_node_name(node_result: object) -> str | None:
    """Extract the name from a node execution result."""

    if isinstance(node_result, ModelExecutionResult):
        return node_result.model_name
    if isinstance(node_result, SeedExecutionResult):
        return node_result.seed_name
    return None


def extract_upstream_model_deps(
    plan: PlanOutput,
) -> dict[str, frozenset[str]]:
    """Extract upstream model dependency names for each model in the plan."""

    from sqlbuild.compiler.compile.models import CompiledObjectKey
    from sqlbuild.compiler.compile.types import CompiledResourceType

    result: dict[str, frozenset[str]] = {}
    key: CompiledObjectKey
    for key in plan.execution_order:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        result[key.name] = frozenset(
            dep.name
            for dep in plan.upstream_deps.get(key, ())
            if dep.resource_type == CompiledResourceType.MODEL
        )
    return result


def verify_ordering_invariant(
    *,
    completed_at_start: list[tuple[str, frozenset[str]]],
    upstream_model_deps: dict[str, frozenset[str]],
) -> None:
    """Assert no node started before all its upstream model deps completed."""

    name: str
    completed_snapshot: frozenset[str]
    for name, completed_snapshot in completed_at_start:
        required_deps: frozenset[str] = upstream_model_deps.get(name, frozenset())
        missing: frozenset[str] = required_deps - completed_snapshot
        assert not missing, (
            f"Node '{name}' started before upstream deps completed: "
            f"missing={missing}, completed={completed_snapshot}"
        )


def verify_concurrent_warehouse_state(
    *,
    db_path: Path,
    adapter: DuckDbAdapter,
    test_case: ConcurrentBuildTestCase,
) -> None:
    """Verify warehouse state via a fresh read-only connection."""

    connection: Any = adapter.connect({"database": str(db_path)})
    try:
        query: str
        expected_rows: tuple[tuple[object, ...], ...]
        for query, expected_rows in test_case.expected_query_results:
            cursor: Any = connection.execute(query)
            actual_rows: tuple[tuple[object, ...], ...] = tuple(
                tuple(row) for row in cursor.fetchall()
            )
            assert actual_rows == expected_rows, (
                f"Query: {query}\nExpected: {expected_rows}\nActual: {actual_rows}"
            )

        relation: str
        for relation in test_case.expected_missing_relations:
            parts: list[str] = relation.split(".")
            schema: str | None = parts[0] if len(parts) > 1 else None
            name: str = parts[-1]
            cursor = connection.execute(
                "SELECT 1 FROM information_schema.tables "
                f"WHERE table_name = '{name}'"
                + (f" AND table_schema = '{schema}'" if schema else "")
            )
            assert cursor.fetchone() is None, f"Relation {relation} should not exist"
    finally:
        adapter.close(connection)
