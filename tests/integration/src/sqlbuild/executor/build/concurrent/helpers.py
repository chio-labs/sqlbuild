"""Test helpers for concurrent build execution tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineOptions, CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.main._execute import execute_build_plan
from sqlbuild.executor.build.models import (
    BuildCustomizations,
    BuildExecutionResult,
    BuildRuntimeParams,
    SeedExecutionResult,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.provider.main.session import build_provider_session
from sqlbuild.runtime.contracts.types import ExecutionResourceKind, NodeStartCallback
from tests.integration.src.sqlbuild.executor.build.concurrent._test_types import (
    ConcurrentBuildTestCase,
)


class _NoProviderSession:
    providers: None = None

    def close(self) -> None:
        return None


def _build_real_provider_session(discovered: DiscoveredProjectInputs) -> Any:
    return build_provider_session(discovered_providers=discovered.providers)


def _build_no_provider_session(_discovered: DiscoveredProjectInputs) -> _NoProviderSession:
    return _NoProviderSession()


_PROVIDER_SESSION_BUILDERS: dict[bool, Callable[[DiscoveredProjectInputs], Any]] = {
    True: _build_real_provider_session,
    False: _build_no_provider_session,
}


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
    provider_session: Any = _PROVIDER_SESSION_BUILDERS[test_case.use_provider_session](discovered)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered,
        adapter=adapter,
        options=CompilePipelineOptions(no_sql_validation=True, connection_config=config),
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
            connection_config=config,
            connections=tuple(worker_connections),
            scheduler_connection=scheduler_connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.STAGED,
                run_id="test_concurrent",
                query_change_tracking=True,
                run_audits=test_case.run_audits,
                fail_fast=test_case.fail_fast,
                providers=provider_session.providers,
            ),
            customizations=BuildCustomizations(
                loader_functions=discovered.loader_functions,
            ),
        )
    finally:
        provider_session.close()
        conn: Any
        for conn in worker_connections:
            adapter.close(conn)
        adapter.close(scheduler_connection)


def build_ordering_trace_callbacks(
    *,
    completed_at_start: list[tuple[str, frozenset[str]]],
    completed_names: set[str],
    lock: threading.Lock,
) -> tuple[NodeStartCallback, Any]:
    """Build on_node_start/on_node_complete callbacks that record ordering traces."""

    def on_node_start(name: str, *, resource_kind: ExecutionResourceKind) -> None:
        del resource_kind
        with lock:
            snapshot: frozenset[str] = frozenset(completed_names)
            completed_at_start.append((name, snapshot))

    def on_node_complete(node_result: object) -> None:
        _NODE_COMPLETION_HANDLERS.get(type(node_result), _ignore_node_completion)(
            node_result=node_result,
            completed_names=completed_names,
            lock=lock,
        )

    return on_node_start, on_node_complete


def _record_model_completion(
    *, node_result: object, completed_names: set[str], lock: threading.Lock
) -> None:
    with lock:
        completed_names.add(cast(ModelExecutionResult, node_result).model_name)


def _record_seed_completion(
    *, node_result: object, completed_names: set[str], lock: threading.Lock
) -> None:
    with lock:
        completed_names.add(cast(SeedExecutionResult, node_result).seed_name)


def _ignore_node_completion(
    *, node_result: object, completed_names: set[str], lock: threading.Lock
) -> None:
    del node_result, completed_names, lock


_NODE_COMPLETION_HANDLERS: dict[type[object], Callable[..., None]] = {
    ModelExecutionResult: _record_model_completion,
    SeedExecutionResult: _record_seed_completion,
}


def extract_upstream_model_deps(
    plan: PlanOutput,
) -> dict[str, frozenset[str]]:
    """Extract upstream model dependency names for each model in the plan."""

    from sqlbuild.compiler.compile.models import CompiledObjectKey
    from sqlbuild.compiler.compile.types import CompiledResourceType

    dependencies_by_resource_type: dict[object, dict[str, frozenset[str]]] = {
        resource_type: {} for resource_type in CompiledResourceType
    }
    key: CompiledObjectKey
    for key in plan.execution_order:
        deps_by_resource_type: dict[object, list[str]] = {
            resource_type: [] for resource_type in CompiledResourceType
        }
        for dep in plan.upstream_deps.get(key, ()):
            deps_by_resource_type[dep.resource_type].append(dep.name)
        dependencies_by_resource_type[key.resource_type][key.name] = frozenset(
            deps_by_resource_type[CompiledResourceType.MODEL]
        )
    return dependencies_by_resource_type[CompiledResourceType.MODEL]


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
            schema: str
            name: str
            schema, _, name = relation.rpartition(".")
            name = name or schema
            schema = schema.removesuffix(name)
            cursor = connection.execute(
                "SELECT 1 FROM information_schema.tables "
                f"WHERE table_name = '{name}'" + f" AND table_schema = '{schema}'" * bool(schema)
            )
            assert cursor.fetchone() is None, f"Relation {relation} should not exist"
    finally:
        adapter.close(connection)
