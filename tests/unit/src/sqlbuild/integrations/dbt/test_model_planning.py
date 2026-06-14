from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.model_planning import build_dbt_model_planning_result
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtModelPlanEntry,
    DbtModelPlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import build_merged_dbt_execution_argv
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtModelPlanAction,
    DbtModelPlanReason,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtExecutionArgvPruningTestCase,
    DbtModelPlanningTestCase,
    DbtModelSourceBlockingTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_compiled_project_with_models,
    build_manifest_data,
    build_manifest_model_node,
    build_manifest_source_node,
    setup_dbt_model_planning_state,
    write_dbt_test_fingerprint,
)

MODEL_PLANNING_TEST_CASES: tuple[DbtModelPlanningTestCase, ...] = (
    DbtModelPlanningTestCase(
        description="missing fingerprint plans first run",
        create_relation=False,
        fingerprint_hash=None,
        expected_action=DbtModelPlanAction.RUN,
        expected_reason=DbtModelPlanReason.FIRST_RUN,
    ),
    DbtModelPlanningTestCase(
        description="missing relation plans rerun",
        create_relation=False,
        fingerprint_hash="same_hash",
        expected_action=DbtModelPlanAction.RUN,
        expected_reason=DbtModelPlanReason.RELATION_MISSING,
    ),
    DbtModelPlanningTestCase(
        description="checksum change plans rerun",
        create_relation=True,
        fingerprint_hash="old_hash",
        expected_action=DbtModelPlanAction.RUN,
        expected_reason=DbtModelPlanReason.CHECKSUM_CHANGED,
    ),
    DbtModelPlanningTestCase(
        description="matching checksum and relation plans current",
        create_relation=True,
        fingerprint_hash="same_hash",
        expected_action=DbtModelPlanAction.CURRENT,
        expected_reason=DbtModelPlanReason.NO_CHANGE,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    MODEL_PLANNING_TEST_CASES,
    ids=[case.description for case in MODEL_PLANNING_TEST_CASES],
)
def test_given_dbt_model_state_when_planning_then_returns_expected_action(
    test_case: DbtModelPlanningTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "dbt_model_plan.duckdb")})
    project: CompiledProject = replace(
        build_compiled_project_with_models({}),
        effective_target_schema="main",
        effective_target_database=None,
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    schema="main",
                    alias="orders",
                    checksum="same_hash",
                ),
            )
        )
    )
    try:
        setup_dbt_model_planning_state(
            adapter=adapter,
            connection=connection,
            unique_id="model.analytics.orders",
            create_relation=test_case.create_relation,
            fingerprint_hash=test_case.fingerprint_hash,
        )

        result: DbtModelPlanningResult = build_dbt_model_planning_result(
            manifest=manifest,
            candidate_unique_ids=("model.analytics.orders",),
            project=project,
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert len(result.entries) == 1
    assert result.entries[0].action == test_case.expected_action
    assert result.entries[0].reason == test_case.expected_reason


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionArgvPruningTestCase(
            description="pruned execution argv keeps runnable models and non-model resources",
            expected_argv=(
                "dbt",
                "build",
                "--full-refresh",
                "--select",
                "run_me",
                "seed.analytics.country_codes",
            ),
        )
    ],
    ids=["pruned execution argv keeps runnable models and non-model resources"],
)
def test_given_dbt_model_plan_when_building_execution_argv_then_selects_runnable_work(
    test_case: DbtExecutionArgvPruningTestCase,
) -> None:
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(
            DbtLsNode(unique_id="model.analytics.run_me", resource_type="model"),
            DbtLsNode(unique_id="model.analytics.current", resource_type="model"),
            DbtLsNode(unique_id="seed.analytics.country_codes", resource_type="seed"),
        ),
        dbt_selected_unique_ids=(
            "model.analytics.current",
            "model.analytics.run_me",
            "seed.analytics.country_codes",
        ),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                DbtModelPlanEntry(
                    unique_id="model.analytics.current",
                    package_name="analytics",
                    name="current",
                    action=DbtModelPlanAction.CURRENT,
                    reason=DbtModelPlanReason.NO_CHANGE,
                    relation_name="main.current",
                ),
                DbtModelPlanEntry(
                    unique_id="model.analytics.run_me",
                    package_name="analytics",
                    name="run_me",
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.CHECKSUM_CHANGED,
                    relation_name="main.run_me",
                ),
            )
        ),
    )

    argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=DbtInteropCommand.BUILD,
        options=DbtCliOptions(),
        routed_args=("--select", "tag:daily", "--exclude", "tag:slow", "--full-refresh"),
        plan=plan,
    )

    assert argv == test_case.expected_argv


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionArgvPruningTestCase(
            description="current model plan skips dbt even when selected tests are present",
            expected_argv=None,
        )
    ],
    ids=["current model plan skips dbt even when selected tests are present"],
)
def test_given_current_dbt_model_plan_when_building_execution_argv_then_skips_dbt(
    test_case: DbtExecutionArgvPruningTestCase,
) -> None:
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(
            DbtLsNode(unique_id="model.analytics.current", resource_type="model"),
            DbtLsNode(unique_id="test.analytics.not_null_current", resource_type="test"),
        ),
        dbt_selected_unique_ids=(
            "model.analytics.current",
            "test.analytics.not_null_current",
        ),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                DbtModelPlanEntry(
                    unique_id="model.analytics.current",
                    package_name="analytics",
                    name="current",
                    action=DbtModelPlanAction.CURRENT,
                    reason=DbtModelPlanReason.NO_CHANGE,
                    relation_name="main.current",
                ),
            )
        ),
    )

    argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=DbtInteropCommand.BUILD,
        options=DbtCliOptions(),
        routed_args=("--select", "+current+"),
        plan=plan,
    )

    assert argv == test_case.expected_argv


@pytest.mark.parametrize(
    "test_case",
    [
        DbtModelSourceBlockingTestCase(
            description="source age error blocks downstream dbt and SQLBuild models",
            expected_blocked_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
            expected_blocked_sqlbuild_model_names=("downstream_orders",),
            expected_blocked_source_unique_ids=("source.analytics.raw.orders",),
        )
    ],
    ids=["source age error blocks downstream dbt and SQLBuild models"],
)
def test_given_dbt_source_age_error_when_planning_then_blocks_downstream_models(
    test_case: DbtModelSourceBlockingTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "dbt_source_blocking.duckdb")})
    project: CompiledProject = replace(
        build_compiled_project_with_models(
            {"downstream_orders": 'select * from __dbt_ref("fact_orders")'}
        ),
        effective_target_schema="main",
        effective_target_database=None,
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.stg_orders",
                    package_name="analytics",
                    name="stg_orders",
                    schema="main",
                    alias="stg_orders",
                    checksum="same_hash",
                    depends_on_nodes=("source.analytics.raw.orders",),
                ),
                build_manifest_model_node(
                    unique_id="model.analytics.fact_orders",
                    package_name="analytics",
                    name="fact_orders",
                    schema="main",
                    alias="fact_orders",
                    checksum="same_hash",
                    depends_on_nodes=("model.analytics.stg_orders",),
                ),
            ),
            sources=(
                build_manifest_source_node(
                    unique_id="source.analytics.raw.orders",
                    source_name="raw",
                    name="orders",
                    schema="main",
                    identifier="raw_orders",
                    loaded_at_field="loaded_at",
                    freshness={"error_after": {"count": 1, "period": "day"}},
                ),
            ),
        )
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    try:
        adapter.execute(
            connection,
            "CREATE TABLE main.raw_orders AS SELECT TIMESTAMP '2000-01-01 00:00:00' AS loaded_at",
        )
        adapter.execute(connection, "CREATE TABLE main.stg_orders AS SELECT 1 AS id")
        adapter.execute(connection, "CREATE TABLE main.fact_orders AS SELECT 1 AS id")
        write_dbt_test_fingerprint(
            adapter=adapter,
            connection=connection,
            unique_id="model.analytics.stg_orders",
            version_hash="same_hash",
        )
        write_dbt_test_fingerprint(
            adapter=adapter,
            connection=connection,
            unique_id="model.analytics.fact_orders",
            version_hash="same_hash",
        )

        result: DbtModelPlanningResult = build_dbt_model_planning_result(
            manifest=manifest,
            candidate_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
            project=project,
            graph=graph,
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert result.blocked_unique_ids == test_case.expected_blocked_unique_ids
    assert result.blocked_sqlbuild_model_names == test_case.expected_blocked_sqlbuild_model_names
    assert all(
        entry.blocked_source_unique_ids == test_case.expected_blocked_source_unique_ids
        for entry in result.entries
    )
    assert all(
        entry.reason == DbtModelPlanReason.SOURCE_FRESHNESS_ERROR for entry in result.entries
    )
