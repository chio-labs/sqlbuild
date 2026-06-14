"""Unit tests for build scheduler source loader nodes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction, DiscoveredLoaderFunction
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SourceLoadPlanEntry
from sqlbuild.compiler.planner.types import PlanAction, PlanReason
from sqlbuild.executor.build.main.execute import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import HookContext
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.models import PythonHookEntry
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy
from tests.unit.src.sqlbuild.executor.build.helpers._test_types import (
    BuildSchedulerModelHookTestCase,
    BuildSchedulerPlannedSkipTestCase,
    BuildSchedulerPreHookSkipTestCase,
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

BUILD_SCHEDULER_MODEL_HOOK_TEST_CASES: list[BuildSchedulerModelHookTestCase] = [
    BuildSchedulerModelHookTestCase(
        description="hook runs before model materialization",
        hook_raises=False,
        expected_model_status=ExecutionStatus.SUCCESS,
        expected_events=("start:hook_model", "hook:hook_model"),
        expected_model_rows=((1,),),
    ),
    BuildSchedulerModelHookTestCase(
        description="hook failure marks model failed",
        hook_raises=True,
        expected_model_status=ExecutionStatus.FAILED,
        expected_events=("start:hook_model", "hook:hook_model"),
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
                destination="raw_orders",
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


@pytest.mark.parametrize(
    "test_case",
    BUILD_SCHEDULER_MODEL_HOOK_TEST_CASES,
    ids=[case.description for case in BUILD_SCHEDULER_MODEL_HOOK_TEST_CASES],
)
def test_given_model_materialize_hook_when_build_runs_then_it_prepares_or_fails_model(
    test_case: BuildSchedulerModelHookTestCase,
    tmp_path: Path,
) -> None:
    model_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "hook_model")
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "scheduler_hook.duckdb")})
    events: list[str] = []
    plan: PlanOutput = PlanOutput(
        execution_order=(model_key,),
        selected_keys=frozenset({model_key}),
        model_entries=(
            build_model_plan_entry(
                name="hook_model",
                resolved_sql="SELECT id FROM hook_seed",
            ),
        ),
    )

    def before_model_materialize(entry: ModelPlanEntry, hook_connection: object) -> None:
        events.append(f"hook:{entry.name}")
        hook_actions: dict[bool, Callable[[], object]] = {
            True: lambda: (_ for _ in ()).throw(RuntimeError("hook failed")),
            False: lambda: adapter.execute(
                hook_connection, "CREATE TABLE hook_seed AS SELECT 1 AS id"
            ),
        }
        hook_actions[test_case.hook_raises]()

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "scheduler_hook.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            promotion_mode=TablePromotionMode.DIRECT,
            run_id="run-1",
            run_audits=False,
            run_tests=False,
            on_node_start=lambda name, _kind: events.append(f"start:{name}"),
            before_model_materialize=before_model_materialize,
        )
        loaded_rows: tuple[tuple[object, ...], ...] = fetch_rows_or_empty(
            connection,
            "SELECT id FROM hook_model ORDER BY id",
        )
    finally:
        adapter.close(connection)

    assert result.model_results[0].status == test_case.expected_model_status
    assert tuple(events) == test_case.expected_events
    assert loaded_rows == test_case.expected_model_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerPreHookSkipTestCase(
            description="pre-hook skip blocks downstream model",
            expected_model_statuses=(ExecutionStatus.SKIPPED, ExecutionStatus.SKIPPED),
            expected_execution_order=("upstream_model",),
        )
    ],
    ids=["pre-hook skip blocks downstream model"],
)
def test_given_model_pre_hook_skips_when_build_runs_then_downstream_model_is_skipped(
    test_case: BuildSchedulerPreHookSkipTestCase,
    tmp_path: Path,
) -> None:
    upstream_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.MODEL, "upstream_model"
    )
    downstream_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.MODEL, "downstream_model"
    )
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "scheduler_skip.duckdb")})
    node_starts: list[str] = []

    def maybe_skip(ctx: HookContext) -> object:
        return ctx.skip("upstream disabled")

    plan: PlanOutput = PlanOutput(
        execution_order=(upstream_key, downstream_key),
        selected_keys=frozenset({upstream_key, downstream_key}),
        model_entries=(
            build_model_plan_entry(
                name="upstream_model",
                resolved_sql="SELECT 1 AS id",
            ),
            build_model_plan_entry(
                name="downstream_model",
                resolved_sql="SELECT id FROM upstream_model",
            ),
        ),
        upstream_deps={upstream_key: (), downstream_key: (upstream_key,)},
        downstream_deps={upstream_key: (downstream_key,), downstream_key: ()},
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/maybe_skip.py"),
                name="maybe_skip",
                function=maybe_skip,
            ),
        ),
    )
    plan = replace(
        plan,
        model_entries=(
            replace(
                plan.model_entries[0],
                pre_hooks=(PythonHookEntry(name="maybe_skip", kwargs={}),),
            ),
            plan.model_entries[1],
        ),
    )

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "scheduler_skip.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            promotion_mode=TablePromotionMode.DIRECT,
            run_id="run-1",
            run_audits=False,
            run_tests=False,
            on_node_start=lambda name, _kind: node_starts.append(name),
        )
    finally:
        adapter.close(connection)

    assert tuple(model.status for model in result.model_results) == (
        test_case.expected_model_statuses
    )
    assert tuple(node_starts) == test_case.expected_execution_order


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerPlannedSkipTestCase(
            description="planned source freshness skip blocks downstream model",
            expected_model_statuses=(ExecutionStatus.SKIPPED, ExecutionStatus.SKIPPED),
            expected_build_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_skip_reason="Blocked by source freshness error",
            expected_execution_order=("upstream_model",),
        )
    ],
    ids=["planned source freshness skip blocks downstream model"],
)
def test_given_model_plan_action_skip_when_build_runs_then_downstream_model_is_skipped(
    test_case: BuildSchedulerPlannedSkipTestCase,
    tmp_path: Path,
) -> None:
    upstream_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.MODEL, "upstream_model"
    )
    downstream_key: CompiledObjectKey = CompiledObjectKey(
        CompiledResourceType.MODEL, "downstream_model"
    )
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect(
        {"database": str(tmp_path / "scheduler_planned_skip.duckdb")}
    )
    node_starts: list[str] = []
    plan: PlanOutput = PlanOutput(
        execution_order=(upstream_key, downstream_key),
        selected_keys=frozenset({upstream_key, downstream_key}),
        model_entries=(
            build_model_plan_entry(
                name="upstream_model",
                action=PlanAction.SKIP,
                reason=PlanReason.SOURCE_FRESHNESS_ERROR,
                resolved_sql="SELECT 1 AS id",
            ),
            build_model_plan_entry(
                name="downstream_model",
                resolved_sql="SELECT id FROM upstream_model",
            ),
        ),
        upstream_deps={upstream_key: (), downstream_key: (upstream_key,)},
        downstream_deps={upstream_key: (downstream_key,), downstream_key: ()},
    )

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "scheduler_planned_skip.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            promotion_mode=TablePromotionMode.DIRECT,
            run_id="run-1",
            run_audits=False,
            run_tests=False,
            on_node_start=lambda name, _kind: node_starts.append(name),
        )
    finally:
        adapter.close(connection)

    assert tuple(model.status for model in result.model_results) == (
        test_case.expected_model_statuses
    )
    assert result.status == test_case.expected_build_status
    assert result.failure_count == test_case.expected_failure_count
    assert result.model_results[0].skip_reason == test_case.expected_skip_reason
    assert tuple(node_starts) == test_case.expected_execution_order
