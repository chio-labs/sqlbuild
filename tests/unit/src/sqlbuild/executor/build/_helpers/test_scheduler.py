"""Unit tests for build scheduler source loader nodes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    PythonHookEntry,
)
from sqlbuild.compiler.node_source_watermarks.constants import NODE_SOURCE_WATERMARK_TABLE_NAME
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkRecord
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SourceLoadPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.executor.build.main.execute import execute_build_plan
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildCustomizations,
    BuildExecutionResult,
    BuildRuntimeParams,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import HookContext
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.spec.contracts.models import SourceEntry
from sqlbuild.spec.contracts.types import SourceWriteStrategy
from tests.unit.src.sqlbuild.executor.build._helpers._test_types import (
    BuildSchedulerMergedUpstreamWatermarkTestCase,
    BuildSchedulerModelHookTestCase,
    BuildSchedulerNodeSourceWatermarkPayloadTestCase,
    BuildSchedulerNodeSourceWatermarkTestCase,
    BuildSchedulerPlannedSkipTestCase,
    BuildSchedulerPreHookSkipTestCase,
    BuildSchedulerSourceLoadTestCase,
)
from tests.unit.src.sqlbuild.executor.build._helpers.helpers import (
    build_discovered_source_loader,
    build_failing_discovered_source_loader,
    build_model_plan_entry,
    build_source_freshness_record,
    fetch_rows_or_empty,
    node_source_hashes_by_name,
    node_source_kinds_by_name,
    node_source_unknown_reasons_by_name,
    read_node_source_watermark_records,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerSourceLoadTestCase(
            description="failed managed source blocks downstream model",
            source_status=ExecutionStatus.FAILED,
            loader_factory=build_failing_discovered_source_loader,
            expected_load_status=ExecutionStatus.FAILED,
            expected_model_status=ExecutionStatus.SKIPPED,
            expected_execution_order=("raw_orders",),
        ),
        BuildSchedulerSourceLoadTestCase(
            description="successful managed source runs before downstream model",
            source_status=ExecutionStatus.SUCCESS,
            loader_factory=build_discovered_source_loader,
            expected_load_status=ExecutionStatus.SUCCESS,
            expected_model_status=ExecutionStatus.SUCCESS,
            expected_execution_order=("raw_orders", "stg_orders"),
            expected_model_rows=((1, "loaded"),),
        ),
    ],
    ids=lambda case: case.description,
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
    loader_function: DiscoveredLoaderFunction = test_case.loader_factory(loader_name=loader_name)
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
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
            callbacks=BuildCallbacks(
                on_node_start=lambda name, *, resource_kind: node_starts.append(name),
            ),
            customizations=BuildCustomizations(
                loader_functions=(loader_function,),
            ),
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
    [
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
    ],
    ids=lambda case: case.description,
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

    def before_model_materialize(entry: ModelPlanEntry, *, connection: object) -> None:
        events.append(f"hook:{entry.name}")
        hook_actions: dict[bool, Callable[[], object]] = {
            True: lambda: (_ for _ in ()).throw(RuntimeError("hook failed")),
            False: lambda: adapter.execute(
                connection=connection, sql="CREATE TABLE hook_seed AS SELECT 1 AS id"
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
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
            callbacks=BuildCallbacks(
                on_node_start=lambda name, *, resource_kind: events.append(f"start:{name}"),
                before_model_materialize=before_model_materialize,
            ),
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
        BuildSchedulerNodeSourceWatermarkTestCase(
            description="successful model writes node source watermark",
            expected_rows=((CompiledResourceType.MODEL.value, "stg_orders", "run-1"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_when_model_succeeds_then_writes_node_source_watermark(
    test_case: BuildSchedulerNodeSourceWatermarkTestCase,
    tmp_path: Path,
) -> None:
    model_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "stg_orders")
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "watermarks.duckdb")})
    plan: PlanOutput = PlanOutput(
        execution_order=(model_key,),
        selected_keys=frozenset({model_key}),
        model_entries=(build_model_plan_entry(name="stg_orders"),),
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders",
                schema="main",
                table="raw_orders",
            )
        },
        upstream_deps={model_key: (source_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                SourceFreshnessRecord(
                    source_name="raw_orders",
                    target_database=None,
                    target_schema="main",
                    target_name="raw_orders",
                    run_id="run-1",
                    strategy="adapter",
                    value_kind="timestamp",
                    data_version="2026-06-30T12:00:00",
                    data_version_hash="source-version",
                    observed_at=datetime(2026, 6, 30, 12, 1),
                ),
            )
        ),
    )

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "watermarks.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
        )
        rows: tuple[tuple[object, ...], ...] = tuple(
            connection.execute(
                f"SELECT node_type, node_name, run_id FROM {NODE_SOURCE_WATERMARK_TABLE_NAME}"
            ).fetchall()
        )
    finally:
        adapter.close(connection)

    assert result.status == BuildStatus.SUCCESS
    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerNodeSourceWatermarkPayloadTestCase(
            description="same run upstream table watermark is inherited downstream",
            expected_source_hashes_by_node={"b": ("source-version",), "a": ("source-version",)},
            expected_source_kinds_by_node={"b": ("direct",), "a": ("inherited",)},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_table_runs_before_downstream_when_build_succeeds_then_inherits_watermark(
    test_case: BuildSchedulerNodeSourceWatermarkPayloadTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    b_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "b")
    a_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "a")
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "same_run.duckdb")})
    plan: PlanOutput = PlanOutput(
        execution_order=(b_key, a_key),
        selected_keys=frozenset({b_key, a_key}),
        model_entries=(
            build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),
            build_model_plan_entry(name="a", resolved_sql="SELECT id FROM b"),
        ),
        source_map={
            "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
        },
        upstream_deps={b_key: (source_key,), a_key: (b_key,)},
        downstream_deps={source_key: (b_key,), b_key: (a_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="source-version",
                ),
            )
        ),
    )

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "same_run.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
        )
        records: dict[str, NodeSourceWatermarkRecord] = read_node_source_watermark_records(
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert result.status == BuildStatus.SUCCESS
    assert (
        node_source_hashes_by_name(records, test_case.expected_source_hashes_by_node)
        == test_case.expected_source_hashes_by_node
    )
    assert (
        node_source_kinds_by_name(records, test_case.expected_source_kinds_by_node)
        == test_case.expected_source_kinds_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerNodeSourceWatermarkPayloadTestCase(
            description="downstream table reaches source frontier through view",
            expected_source_hashes_by_node={"a": ("source-version",)},
            expected_source_kinds_by_node={"a": ("direct",)},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_downstream_depends_on_view_over_source_when_built_then_records_direct_watermark(
    test_case: BuildSchedulerNodeSourceWatermarkPayloadTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    view_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "v")
    a_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "a")
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "view_source.duckdb")})
    plan: PlanOutput = PlanOutput(
        execution_order=(view_key, a_key),
        selected_keys=frozenset({view_key, a_key}),
        model_entries=(
            build_model_plan_entry(
                name="v",
                materialization_type=MaterializationType.VIEW,
                resolved_sql="SELECT 1 AS id",
            ),
            build_model_plan_entry(name="a", resolved_sql="SELECT id FROM v"),
        ),
        source_map={
            "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
        },
        upstream_deps={view_key: (source_key,), a_key: (view_key,)},
        downstream_deps={source_key: (view_key,), view_key: (a_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="source-version",
                ),
            )
        ),
    )

    try:
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "view_source.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
        )
        records: dict[str, NodeSourceWatermarkRecord] = read_node_source_watermark_records(
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert result.status == BuildStatus.SUCCESS
    assert "v" not in records
    assert (
        node_source_hashes_by_name(records, test_case.expected_source_hashes_by_node)
        == test_case.expected_source_hashes_by_node
    )
    assert (
        node_source_kinds_by_name(records, test_case.expected_source_kinds_by_node)
        == test_case.expected_source_kinds_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerNodeSourceWatermarkPayloadTestCase(
            description="downstream table reaches materialized frontier through view",
            expected_source_hashes_by_node={"a": ("old-source-version",)},
            expected_source_kinds_by_node={"a": ("inherited",)},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_downstream_depends_on_view_over_table_when_built_then_inherits_table_watermark(
    test_case: BuildSchedulerNodeSourceWatermarkPayloadTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    b_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "b")
    view_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "v")
    a_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "a")
    adapter: DuckDbAdapter = DuckDbAdapter()
    database_path: Path = tmp_path / "view_table.duckdb"
    connection: object = adapter.connect({"database": str(database_path)})
    source_map: dict[str, SourceEntry] = {
        "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
    }
    b_plan: PlanOutput = PlanOutput(
        execution_order=(b_key,),
        selected_keys=frozenset({b_key}),
        model_entries=(build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),),
        source_map=source_map,
        upstream_deps={b_key: (source_key,)},
        downstream_deps={source_key: (b_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="old-source-version",
                    data_version="2026-06-30T11:00:00",
                ),
            )
        ),
    )
    a_plan: PlanOutput = PlanOutput(
        execution_order=(view_key, a_key),
        selected_keys=frozenset({view_key, a_key}),
        model_entries=(
            build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),
            build_model_plan_entry(
                name="v",
                materialization_type=MaterializationType.VIEW,
                resolved_sql="SELECT id FROM b",
            ),
            build_model_plan_entry(name="a", resolved_sql="SELECT id FROM v"),
        ),
        source_map=source_map,
        upstream_deps={b_key: (source_key,), view_key: (b_key,), a_key: (view_key,)},
        downstream_deps={source_key: (b_key,), b_key: (view_key,), view_key: (a_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="current-source-version",
                    data_version="2026-06-30T12:00:00",
                ),
            )
        ),
    )

    try:
        b_result: BuildExecutionResult = execute_build_plan(
            plan=b_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-b",
                run_audits=False,
                run_tests=False,
            ),
        )
        a_result: BuildExecutionResult = execute_build_plan(
            plan=a_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-a",
                run_audits=False,
                run_tests=False,
            ),
        )
        records: dict[str, NodeSourceWatermarkRecord] = read_node_source_watermark_records(
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert b_result.status == BuildStatus.SUCCESS
    assert a_result.status == BuildStatus.SUCCESS
    assert "v" not in records
    assert (
        node_source_hashes_by_name(records, test_case.expected_source_hashes_by_node)
        == test_case.expected_source_hashes_by_node
    )
    assert (
        node_source_kinds_by_name(records, test_case.expected_source_kinds_by_node)
        == test_case.expected_source_kinds_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerNodeSourceWatermarkPayloadTestCase(
            description="downstream-only build inherits persisted upstream watermark",
            expected_source_hashes_by_node={"a": ("old-source-version",)},
            expected_source_kinds_by_node={"a": ("inherited",)},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_only_downstream_runs_when_upstream_watermark_exists_then_inherits_persisted_value(
    test_case: BuildSchedulerNodeSourceWatermarkPayloadTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    b_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "b")
    a_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "a")
    adapter: DuckDbAdapter = DuckDbAdapter()
    database_path: Path = tmp_path / "persisted.duckdb"
    connection: object = adapter.connect({"database": str(database_path)})
    first_plan: PlanOutput = PlanOutput(
        execution_order=(b_key,),
        selected_keys=frozenset({b_key}),
        model_entries=(build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),),
        source_map={
            "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
        },
        upstream_deps={b_key: (source_key,)},
        downstream_deps={source_key: (b_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="old-source-version",
                ),
            )
        ),
    )
    second_plan: PlanOutput = PlanOutput(
        execution_order=(a_key,),
        selected_keys=frozenset({a_key}),
        model_entries=(
            build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),
            build_model_plan_entry(name="a", resolved_sql="SELECT id FROM b"),
        ),
        source_map={
            "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
        },
        upstream_deps={b_key: (source_key,), a_key: (b_key,)},
        downstream_deps={source_key: (b_key,), b_key: (a_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="new-source-version",
                ),
            )
        ),
    )

    try:
        first_result: BuildExecutionResult = execute_build_plan(
            plan=first_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
        )
        second_result: BuildExecutionResult = execute_build_plan(
            plan=second_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-2",
                run_audits=False,
                run_tests=False,
            ),
        )
        records: dict[str, NodeSourceWatermarkRecord] = read_node_source_watermark_records(
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert first_result.status == BuildStatus.SUCCESS
    assert second_result.status == BuildStatus.SUCCESS
    assert (
        node_source_hashes_by_name(records, test_case.expected_source_hashes_by_node)
        == test_case.expected_source_hashes_by_node
    )
    assert (
        node_source_kinds_by_name(records, test_case.expected_source_kinds_by_node)
        == test_case.expected_source_kinds_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerNodeSourceWatermarkPayloadTestCase(
            description="missing upstream watermark records unknown source",
            expected_source_hashes_by_node={"a": ()},
            expected_source_kinds_by_node={"a": ()},
            expected_unknown_reasons_by_node={"a": ("missing_upstream_watermark",)},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_table_without_watermark_when_downstream_runs_then_records_unknown(
    test_case: BuildSchedulerNodeSourceWatermarkPayloadTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    b_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "b")
    a_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "a")
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": str(tmp_path / "missing.duckdb")})
    plan: PlanOutput = PlanOutput(
        execution_order=(a_key,),
        selected_keys=frozenset({a_key}),
        model_entries=(
            build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),
            build_model_plan_entry(name="a", resolved_sql="SELECT id FROM b"),
        ),
        source_map={
            "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
        },
        upstream_deps={b_key: (source_key,), a_key: (b_key,)},
        downstream_deps={source_key: (b_key,), b_key: (a_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="new-source-version",
                ),
            )
        ),
    )

    try:
        adapter.execute(connection=connection, sql="CREATE TABLE b AS SELECT 1 AS id")
        result: BuildExecutionResult = execute_build_plan(
            plan=plan,
            adapter=adapter,
            connection_config={"database": str(tmp_path / "missing.duckdb")},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
        )
        records: dict[str, NodeSourceWatermarkRecord] = read_node_source_watermark_records(
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert result.status == BuildStatus.SUCCESS
    assert (
        node_source_hashes_by_name(records, test_case.expected_source_hashes_by_node)
        == test_case.expected_source_hashes_by_node
    )
    assert (
        node_source_kinds_by_name(records, test_case.expected_source_kinds_by_node)
        == test_case.expected_source_kinds_by_node
    )
    assert (
        node_source_unknown_reasons_by_name(records, test_case.expected_unknown_reasons_by_node)
        == test_case.expected_unknown_reasons_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerMergedUpstreamWatermarkTestCase(
            description="both upstream frontier tables have current source watermark",
            b_data_hash="current-source-version",
            b_data_version="2026-06-30T12:00:00",
            c_data_hash="current-source-version",
            c_data_version="2026-06-30T12:00:00",
            expected_source_hashes_by_node={"a": ("current-source-version",)},
            expected_source_kinds_by_node={"a": ("inherited",)},
        ),
        BuildSchedulerMergedUpstreamWatermarkTestCase(
            description="both upstream frontier tables have stale source watermark",
            b_data_hash="old-source-version",
            b_data_version="2026-06-30T11:00:00",
            c_data_hash="old-source-version",
            c_data_version="2026-06-30T11:00:00",
            expected_source_hashes_by_node={"a": ("old-source-version",)},
            expected_source_kinds_by_node={"a": ("inherited",)},
        ),
        BuildSchedulerMergedUpstreamWatermarkTestCase(
            description="one upstream frontier table stale and one current keeps stale watermark",
            b_data_hash="old-source-version",
            b_data_version="2026-06-30T11:00:00",
            c_data_hash="current-source-version",
            c_data_version="2026-06-30T12:00:00",
            expected_source_hashes_by_node={"a": ("old-source-version",)},
            expected_source_kinds_by_node={"a": ("inherited",)},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_downstream_depends_on_two_frontier_tables_when_built_then_merges_oldest_watermark(
    test_case: BuildSchedulerMergedUpstreamWatermarkTestCase,
    tmp_path: Path,
) -> None:
    source_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, "raw_orders")
    b_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "b")
    c_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "c")
    a_key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "a")
    adapter: DuckDbAdapter = DuckDbAdapter()
    database_path: Path = tmp_path / "merged_frontier.duckdb"
    connection: object = adapter.connect({"database": str(database_path)})
    source_map: dict[str, SourceEntry] = {
        "raw_orders": SourceEntry(name="raw_orders", schema="main", table="raw_orders")
    }
    b_plan: PlanOutput = PlanOutput(
        execution_order=(b_key,),
        selected_keys=frozenset({b_key}),
        model_entries=(build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),),
        source_map=source_map,
        upstream_deps={b_key: (source_key,)},
        downstream_deps={source_key: (b_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash=test_case.b_data_hash,
                    data_version=test_case.b_data_version,
                ),
            )
        ),
    )
    c_plan: PlanOutput = PlanOutput(
        execution_order=(c_key,),
        selected_keys=frozenset({c_key}),
        model_entries=(build_model_plan_entry(name="c", resolved_sql="SELECT 1 AS id"),),
        source_map=source_map,
        upstream_deps={c_key: (source_key,)},
        downstream_deps={source_key: (c_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash=test_case.c_data_hash,
                    data_version=test_case.c_data_version,
                ),
            )
        ),
    )
    a_plan: PlanOutput = PlanOutput(
        execution_order=(a_key,),
        selected_keys=frozenset({a_key}),
        model_entries=(
            build_model_plan_entry(name="b", resolved_sql="SELECT 1 AS id"),
            build_model_plan_entry(name="c", resolved_sql="SELECT 1 AS id"),
            build_model_plan_entry(name="a", resolved_sql="SELECT b.id FROM b JOIN c USING (id)"),
        ),
        source_map=source_map,
        upstream_deps={b_key: (source_key,), c_key: (source_key,), a_key: (b_key, c_key)},
        downstream_deps={source_key: (b_key, c_key), b_key: (a_key,), c_key: (a_key,)},
        source_freshness=StandardSourceFreshnessPlanningResult(
            observed_records=(
                build_source_freshness_record(
                    source_name="raw_orders",
                    data_hash="current-source-version",
                    data_version="2026-06-30T12:00:00",
                ),
            )
        ),
    )

    try:
        b_result: BuildExecutionResult = execute_build_plan(
            plan=b_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-b",
                run_audits=False,
                run_tests=False,
            ),
        )
        c_result: BuildExecutionResult = execute_build_plan(
            plan=c_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-c",
                run_audits=False,
                run_tests=False,
            ),
        )
        a_result: BuildExecutionResult = execute_build_plan(
            plan=a_plan,
            adapter=adapter,
            connection_config={"database": str(database_path)},
            connections=(connection,),
            scheduler_connection=connection,
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-a",
                run_audits=False,
                run_tests=False,
            ),
        )
        records: dict[str, NodeSourceWatermarkRecord] = read_node_source_watermark_records(
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert b_result.status == BuildStatus.SUCCESS
    assert c_result.status == BuildStatus.SUCCESS
    assert a_result.status == BuildStatus.SUCCESS
    assert (
        node_source_hashes_by_name(records, test_case.expected_source_hashes_by_node)
        == test_case.expected_source_hashes_by_node
    )
    assert (
        node_source_kinds_by_name(records, test_case.expected_source_kinds_by_node)
        == test_case.expected_source_kinds_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchedulerPreHookSkipTestCase(
            description="pre-hook skip blocks downstream model",
            expected_model_statuses=(ExecutionStatus.SKIPPED, ExecutionStatus.SKIPPED),
            expected_execution_order=("upstream_model",),
        )
    ],
    ids=lambda case: case.description,
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
        return ctx.skip(reason="upstream disabled")

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
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
            callbacks=BuildCallbacks(
                on_node_start=lambda name, *, resource_kind: node_starts.append(name),
            ),
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
    ids=lambda case: case.description,
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
            runtime=BuildRuntimeParams(
                promotion_mode=TablePromotionMode.DIRECT,
                run_id="run-1",
                run_audits=False,
                run_tests=False,
            ),
            callbacks=BuildCallbacks(
                on_node_start=lambda name, *, resource_kind: node_starts.append(name),
            ),
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
