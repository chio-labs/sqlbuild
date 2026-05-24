"""Unit tests for build scheduler source loader nodes."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import PlanOutput, SourceLoadPlanEntry
from sqlbuild.executor.build.main.execute import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy
from tests.unit.src.sqlbuild.executor.build.helpers._test_types import (
    BuildSchedulerSourceLoadTestCase,
)
from tests.unit.src.sqlbuild.executor.build.helpers.helpers import (
    build_discovered_source_loader,
    build_failing_discovered_source_loader,
    build_model_plan_entry,
    fetch_rows_or_empty,
)

BUILD_SCHEDULER_SOURCE_LOAD_TEST_CASES: list[BuildSchedulerSourceLoadTestCase] = [
    BuildSchedulerSourceLoadTestCase(
        description="failed managed source blocks downstream model",
        source_status=ExecutionStatus.FAILED,
        expected_load_status=ExecutionStatus.FAILED,
        expected_model_status=ExecutionStatus.SKIPPED,
        expected_execution_order=("raw_orders",),
    ),
    BuildSchedulerSourceLoadTestCase(
        description="successful managed source runs before downstream model",
        source_status=ExecutionStatus.SUCCESS,
        expected_load_status=ExecutionStatus.SUCCESS,
        expected_model_status=ExecutionStatus.SUCCESS,
        expected_execution_order=("raw_orders", "stg_orders"),
        expected_model_rows=((1, "loaded"),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_SCHEDULER_SOURCE_LOAD_TEST_CASES,
    ids=[case.description for case in BUILD_SCHEDULER_SOURCE_LOAD_TEST_CASES],
)
def test_given_managed_source_node_when_build_runs_then_records_loader_and_blocks_downstream(
    test_case: BuildSchedulerSourceLoadTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    model_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "stg_orders")
    loader_name: str = "raw_orders_loader"
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "scheduler.duckdb")})
    loader_function: DiscoveredLoaderFunction = (
        build_discovered_source_loader(loader_name=loader_name)
        if test_case.source_status == ExecutionStatus.SUCCESS
        else build_failing_discovered_source_loader(loader_name=loader_name)
    )
    node_starts: list[str] = []
    plan: PlanOutput = PlanOutput(
        execution_order=(source_key, model_key),
        selected_keys=frozenset({source_key, model_key}),
        model_entries=(
            build_model_plan_entry(
                name="stg_orders",
                resolved_sql="SELECT id, status FROM raw_orders",
            ),
        ),
        source_load_entries=(
            SourceLoadPlanEntry(
                key=source_key,
                name="raw_orders",
                loader=loader_name,
                target="raw_orders",
            ),
        ),
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders",
                loader=loader_name,
                write_strategy=SourceWriteStrategy.TABLE,
            )
        },
        upstream_deps={model_key: (source_key,)},
        downstream_deps={source_key: (model_key,)},
    )

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "scheduler.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            promotion_mode=TablePromotionMode.DIRECT,
            run_id="run-1",
            run_audits=False,
            run_tests=False,
            loader_functions=(loader_function,),
            on_node_start=lambda name, _kind: node_starts.append(name),
        )
        loaded_rows: tuple[tuple[object, ...], ...] = fetch_rows_or_empty(
            connection,
            "SELECT id, status FROM stg_orders ORDER BY id",
        )
    finally:
        adapter.close(connection)

    assert result.load_results[0].status == test_case.expected_load_status
    assert result.model_results[0].status == test_case.expected_model_status
    assert tuple(node_starts) == test_case.expected_execution_order
    assert loaded_rows == test_case.expected_model_rows
