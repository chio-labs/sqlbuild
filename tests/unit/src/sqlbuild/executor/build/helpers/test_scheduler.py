"""Unit tests for build scheduler source loader nodes."""

from __future__ import annotations

from typing import Any, cast

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.helpers.scheduler import BuildScheduler
from sqlbuild.executor.build.models import BuildIndexes
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.spec.models.project import SnapshotsConfig
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.executor.build.helpers._test_types import (
    BuildSchedulerSourceLoadTestCase,
)
from tests.unit.src.sqlbuild.executor.build.helpers.helpers import build_model_plan_entry

BUILD_SCHEDULER_SOURCE_LOAD_TEST_CASES: list[BuildSchedulerSourceLoadTestCase] = [
    BuildSchedulerSourceLoadTestCase(
        description="failed managed source blocks downstream model",
        source_status=ExecutionStatus.FAILED,
        expected_load_status=ExecutionStatus.FAILED,
        expected_model_status=ExecutionStatus.SKIPPED,
        expected_execution_order=("source:raw_orders",),
    ),
    BuildSchedulerSourceLoadTestCase(
        description="successful managed source runs before downstream model",
        source_status=ExecutionStatus.SUCCESS,
        expected_load_status=ExecutionStatus.SUCCESS,
        expected_model_status=ExecutionStatus.SUCCESS,
        expected_execution_order=("source:raw_orders", "model:stg_orders"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BUILD_SCHEDULER_SOURCE_LOAD_TEST_CASES,
    ids=[case.description for case in BUILD_SCHEDULER_SOURCE_LOAD_TEST_CASES],
)
def test_given_managed_source_node_when_scheduler_runs_then_records_loader_and_blocks_downstream(
    test_case: BuildSchedulerSourceLoadTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    model_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "stg_orders")
    plan: PlanOutput = PlanOutput(
        execution_order=(source_key, model_key),
        selected_keys=frozenset({source_key, model_key}),
        model_entries=(build_model_plan_entry(name="stg_orders"),),
        source_map={"raw_orders": SourceEntry(name="raw_orders", loader="raw_orders_loader")},
        upstream_deps={model_key: (source_key,)},
        downstream_deps={source_key: (model_key,)},
    )
    scheduler: BuildScheduler = BuildScheduler(
        plan=plan,
        indexes=BuildIndexes(model_entries_by_key={model_key: plan.model_entries[0]}),
        adapter=cast(BaseAdapter, object()),
        connections=(object(),),
        scheduler_connection=object(),
        promotion_mode=cast(Any, "staged"),
        run_id="run-1",
        query_change_tracking=True,
        snapshots=SnapshotsConfig(),
        allow_snapshot_schema_change=False,
        run_audits=False,
        run_tests=False,
        fail_fast=False,
        on_node_start=None,
        on_node_complete=None,
        on_progress=None,
    )

    execution_order: list[str] = []

    def execute_source(_key: CompiledObjectKey, _connection: object) -> LoadExecutionResult:
        execution_order.append("source:raw_orders")
        return LoadExecutionResult(
            source_name="raw_orders",
            loader_name="raw_orders_loader",
            status=test_case.source_status,
            target="raw_orders",
        )

    def execute_model(_key: CompiledObjectKey, _connection: object) -> ModelExecutionResult:
        execution_order.append("model:stg_orders")
        return ModelExecutionResult(
            model_name="stg_orders",
            status=ExecutionStatus.SUCCESS,
        )

    monkeypatch.setattr(
        scheduler,
        "_execute_source_node",
        execute_source,
    )
    monkeypatch.setattr(
        scheduler,
        "_execute_model_node",
        execute_model,
    )

    model_results, _seed_results, _function_results, load_results, *_rest = scheduler.run()

    assert load_results[0].status == test_case.expected_load_status
    assert model_results[0].status == test_case.expected_model_status
    assert tuple(execution_order) == test_case.expected_execution_order
