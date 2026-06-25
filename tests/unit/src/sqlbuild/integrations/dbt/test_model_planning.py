from __future__ import annotations

import io
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.fingerprints.main.read import read_latest_fingerprints
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_record
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.manifest.fingerprinting import try_write_dbt_node_fingerprint
from sqlbuild.integrations.dbt.helpers.planning.model_planning import (
    build_dbt_model_planning_result,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandExecutionResult,
    DbtCommandResult,
    DbtExecutionOutcome,
    DbtInteropPlan,
    DbtInteropSelectionResult,
    DbtLsNode,
    DbtModelPlanEntry,
    DbtModelPlanningResult,
    DbtNodeExecutionResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    build_dbt_execution_outcome,
    build_merged_dbt_execution_argv,
    execute_dbt_commands,
)
from sqlbuild.integrations.dbt.types import (
    DbtInteropCommand,
    DbtModelOutcomeState,
    DbtModelPlanAction,
    DbtModelPlanReason,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtExecutionArgvPruningTestCase,
    DbtExecutionOutcomeTestCase,
    DbtExecutionTotalRenderTestCase,
    DbtFingerprintWriteTestCase,
    DbtModelPlanningRelationPrefetchTestCase,
    DbtModelPlanningTestCase,
    DbtModelSourceBlockingTestCase,
    DbtRunResultsFallbackRenderTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    CountingModelPlanningAdapter,
    MappingDbtInvoker,
    RecordingDbtInvoker,
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
    DbtModelPlanningTestCase(
        description="force plans matching checksum and relation for rerun",
        create_relation=True,
        fingerprint_hash="same_hash",
        force=True,
        expected_action=DbtModelPlanAction.RUN,
        expected_reason=DbtModelPlanReason.FORCED,
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
            force=test_case.force,
        )
    finally:
        adapter.close(connection)

    assert len(result.entries) == 1
    assert result.entries[0].action == test_case.expected_action
    assert result.entries[0].reason == test_case.expected_reason


@pytest.mark.parametrize(
    "test_case",
    [
        DbtModelPlanningRelationPrefetchTestCase(
            description="prefetches dbt model relation existence in one bulk call",
            expected_list_relation_call_count=1,
            expected_relation_exists_call_count=0,
            expected_reasons_by_unique_id={
                "model.analytics.base_orders": DbtModelPlanReason.NO_CHANGE,
                "model.analytics.stg_orders": DbtModelPlanReason.RELATION_MISSING,
                "model.analytics.fact_orders": DbtModelPlanReason.NO_CHANGE,
            },
        )
    ],
    ids=["prefetches dbt model relation existence in one bulk call"],
)
def test_given_dbt_model_closure_when_planning_then_prefetches_relation_existence_once(
    test_case: DbtModelPlanningRelationPrefetchTestCase,
    tmp_path: Path,
) -> None:
    adapter: CountingModelPlanningAdapter = CountingModelPlanningAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "dbt_model_prefetch.duckdb")})
    project: CompiledProject = replace(
        build_compiled_project_with_models({}),
        effective_target_schema="main",
        effective_target_database=None,
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.base_orders",
                    package_name="analytics",
                    name="base_orders",
                    schema="main",
                    alias="base_orders",
                    checksum="same_hash",
                ),
                build_manifest_model_node(
                    unique_id="model.analytics.stg_orders",
                    package_name="analytics",
                    name="stg_orders",
                    schema="main",
                    alias="stg_orders",
                    checksum="same_hash",
                    depends_on_nodes=("model.analytics.base_orders",),
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
            )
        )
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    try:
        adapter.execute(connection, "CREATE TABLE main.base_orders AS SELECT 1 AS id")
        adapter.execute(connection, "CREATE TABLE main.fact_orders AS SELECT 1 AS id")
        for unique_id in test_case.expected_reasons_by_unique_id:
            write_dbt_test_fingerprint(
                adapter=adapter,
                connection=connection,
                unique_id=unique_id,
                version_hash="same_hash",
            )
        adapter.list_relation_calls.clear()
        adapter.relation_exists_calls.clear()

        result: DbtModelPlanningResult = build_dbt_model_planning_result(
            manifest=manifest,
            candidate_unique_ids=("model.analytics.fact_orders",),
            project=project,
            graph=graph,
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    entries_by_unique_id: dict[str, DbtModelPlanEntry] = {
        entry.unique_id: entry for entry in result.entries
    }
    assert {
        unique_id: entries_by_unique_id[unique_id].reason
        for unique_id in test_case.expected_reasons_by_unique_id
    } == test_case.expected_reasons_by_unique_id
    assert len(adapter.list_relation_calls) == test_case.expected_list_relation_call_count
    database, schemas, names = adapter.list_relation_calls[0]
    assert database is None
    assert schemas == ("main",)
    assert frozenset(names or ()) == frozenset({"base_orders", "stg_orders", "fact_orders"})
    model_relation_names: frozenset[str] = frozenset({"base_orders", "stg_orders", "fact_orders"})
    assert (
        len(
            tuple(call for call in adapter.relation_exists_calls if call[2] in model_relation_names)
        )
        == test_case.expected_relation_exists_call_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtFingerprintWriteTestCase(
            description="model fingerprint stores SQL definition and metadata separately",
            query_sql="select 1 as order_id",
            node_checksum="checksum_hash",
            expected_definition="select 1 as order_id",
            expected_version_hash="checksum_hash",
            expected_metadata_fragment='"resource_type":"model"',
        )
    ],
    ids=["model fingerprint stores SQL definition and metadata separately"],
)
def test_given_successful_dbt_model_when_writing_fingerprint_then_definition_is_query_sql(
    test_case: DbtFingerprintWriteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "dbt_fingerprint.duckdb")})
    warnings: list[str] = []
    try:
        try_write_dbt_node_fingerprint(
            result=DbtNodeExecutionResult(
                unique_id="model.analytics.orders",
                resource_type="model",
                node_name="orders",
                status="success",
                index=1,
                total=1,
                execution_time=0.1,
                materialized="table",
                relation_name="orders",
                schema="main",
                node_checksum=test_case.node_checksum,
            ),
            adapter=adapter,
            connection=connection,
            run_id="test-run",
            fingerprint_database=None,
            fingerprint_schema="main",
            target_name="dev",
            warnings=warnings,
            query_sql=test_case.query_sql,
        )

        fingerprint_set: FingerprintSet = read_latest_fingerprints(
            connection=connection,
            execute=adapter.execute,
            relation_exists=adapter.relation_exists,
            database=None,
            schema="main",
            render_qualified_name=adapter.render_qualified_name,
            render_read_latest_sql=adapter.render_read_latest_fingerprints_sql,
        )
    finally:
        adapter.close(connection)

    assert warnings == []
    assert fingerprint_set.fingerprints_by_identity is not None
    fingerprint: Fingerprint = fingerprint_set.fingerprints_by_identity[
        (NODE_TYPE_DBT, "model.analytics.orders")
    ]
    assert fingerprint.definition == test_case.expected_definition
    assert fingerprint.version_hash == test_case.expected_version_hash
    assert test_case.expected_metadata_fragment in fingerprint.metadata_json


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionArgvPruningTestCase(
            description="pruned execution argv keeps runnable models and seed names",
            expected_argv=(
                "dbt",
                "build",
                "--full-refresh",
                "--select",
                "country_codes",
                "run_me",
            ),
        )
    ],
    ids=["pruned execution argv keeps runnable models and seed names"],
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
            DbtLsNode(
                unique_id="seed.analytics.country_codes",
                resource_type="seed",
                name="country_codes",
            ),
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
            description="pruned execution argv uses exact fqn selectors",
            expected_argv=(
                "dbt",
                "build",
                "--select",
                "fqn:analytics.marts.orders",
                "fqn:analytics.orders_seed",
                "fqn:analytics.staging.not_null_orders_id",
            ),
        )
    ],
    ids=["pruned execution argv uses exact fqn selectors"],
)
def test_given_dbt_model_plan_with_fqn_when_building_execution_argv_then_selects_exact_nodes(
    test_case: DbtExecutionArgvPruningTestCase,
) -> None:
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(
            DbtLsNode(
                unique_id="model.analytics.orders",
                resource_type="model",
                name="orders",
                fqn=("analytics", "marts", "orders"),
            ),
            DbtLsNode(
                unique_id="model.stripe.orders",
                resource_type="model",
                name="orders",
                fqn=("stripe", "orders"),
            ),
            DbtLsNode(
                unique_id="seed.analytics.orders_seed",
                resource_type="seed",
                name="orders_seed",
                fqn=("analytics", "orders_seed"),
            ),
            DbtLsNode(
                unique_id="test.analytics.not_null_orders_id.abc123",
                resource_type="test",
                name="not_null_orders_id",
                fqn=("analytics", "staging", "not_null_orders_id"),
            ),
        ),
        dbt_selected_unique_ids=(
            "model.analytics.orders",
            "model.stripe.orders",
            "seed.analytics.orders_seed",
            "test.analytics.not_null_orders_id.abc123",
        ),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                DbtModelPlanEntry(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.CHECKSUM_CHANGED,
                    relation_name="main.orders",
                    fqn=("analytics", "marts", "orders"),
                ),
                DbtModelPlanEntry(
                    unique_id="model.stripe.orders",
                    package_name="stripe",
                    name="orders",
                    action=DbtModelPlanAction.CURRENT,
                    reason=DbtModelPlanReason.NO_CHANGE,
                    relation_name="stripe.orders",
                    fqn=("stripe", "orders"),
                ),
            )
        ),
    )

    argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=DbtInteropCommand.BUILD,
        options=DbtCliOptions(),
        routed_args=("--select", "orders"),
        plan=plan,
    )

    assert argv == test_case.expected_argv


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionArgvPruningTestCase(
            description="current model plan skips dbt build when only selected tests remain",
            expected_argv=None,
        )
    ],
    ids=["current model plan skips dbt build when only selected tests remain"],
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
        DbtExecutionArgvPruningTestCase(
            description="current model plan prunes selected seeds",
            expected_argv=None,
        )
    ],
    ids=["current model plan prunes selected seeds"],
)
def test_given_current_dbt_models_and_selected_seed_when_building_execution_argv_then_prunes_seed(
    test_case: DbtExecutionArgvPruningTestCase,
) -> None:
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(
            DbtLsNode(unique_id="model.analytics.current", resource_type="model"),
            DbtLsNode(unique_id="seed.analytics.country_codes", resource_type="seed"),
        ),
        dbt_selected_unique_ids=(
            "model.analytics.current",
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
        DbtExecutionArgvPruningTestCase(
            description="runnable model plan keeps selected tests",
            expected_argv=(
                "dbt",
                "build",
                "--select",
                "not_null_run_me_id",
                "run_me",
            ),
        )
    ],
    ids=["runnable model plan keeps selected tests"],
)
def test_given_runnable_dbt_model_and_selected_test_when_building_execution_argv_then_runs_test(
    test_case: DbtExecutionArgvPruningTestCase,
) -> None:
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(
            DbtLsNode(unique_id="model.analytics.run_me", resource_type="model"),
            DbtLsNode(
                unique_id="test.analytics.not_null_run_me_id",
                resource_type="test",
                name="not_null_run_me_id",
            ),
        ),
        dbt_selected_unique_ids=(
            "model.analytics.run_me",
            "test.analytics.not_null_run_me_id",
        ),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
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
        routed_args=("--select", "+run_me+"),
        plan=plan,
    )

    assert argv == test_case.expected_argv


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionArgvPruningTestCase(
            description="dbt test preserves selected tests even when models are current",
            expected_argv=("dbt", "test", "--select", "not_null_current_id"),
        )
    ],
    ids=["dbt test preserves selected tests even when models are current"],
)
def test_given_current_dbt_model_and_selected_test_when_testing_then_runs_test(
    test_case: DbtExecutionArgvPruningTestCase,
) -> None:
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.TEST,
        dbt_command_argv=("dbt", "test"),
        dbt_selected_nodes=(
            DbtLsNode(unique_id="model.analytics.current", resource_type="model"),
            DbtLsNode(
                unique_id="test.analytics.not_null_current_id",
                resource_type="test",
                name="not_null_current_id",
            ),
        ),
        dbt_selected_unique_ids=(
            "model.analytics.current",
            "test.analytics.not_null_current_id",
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
        command=DbtInteropCommand.TEST,
        options=DbtCliOptions(),
        routed_args=("--select", "not_null_current_id"),
        plan=plan,
    )

    assert argv == test_case.expected_argv


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionOutcomeTestCase(
            description="dbt model outcomes map changed and failed models to SQLBuild overlay",
            expected_states_by_unique_id=(
                ("model.analytics.current", DbtModelOutcomeState.CURRENT),
                ("model.analytics.failed", DbtModelOutcomeState.BLOCKING),
                ("model.analytics.run_me", DbtModelOutcomeState.CHANGED),
            ),
            expected_stale_sqlbuild_model_names=("downstream_run",),
            expected_blocked_sqlbuild_model_names=("downstream_failed",),
        )
    ],
    ids=["dbt model outcomes map changed and failed models to SQLBuild overlay"],
)
def test_given_dbt_node_results_when_building_outcome_then_maps_sqlbuild_overlay(
    test_case: DbtExecutionOutcomeTestCase,
) -> None:
    project: CompiledProject = build_compiled_project_with_models(
        {
            "downstream_run": 'select * from __dbt_ref("run_me")',
            "downstream_failed": 'select * from __dbt_ref("failed")',
        }
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.current",
                    package_name="analytics",
                    name="current",
                ),
                build_manifest_model_node(
                    unique_id="model.analytics.run_me",
                    package_name="analytics",
                    name="run_me",
                ),
                build_manifest_model_node(
                    unique_id="model.analytics.failed",
                    package_name="analytics",
                    name="failed",
                ),
            )
        )
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(),
        dbt_selected_unique_ids=(),
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
                DbtModelPlanEntry(
                    unique_id="model.analytics.failed",
                    package_name="analytics",
                    name="failed",
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.CHECKSUM_CHANGED,
                    relation_name="main.failed",
                ),
            )
        ),
    )

    outcome: DbtExecutionOutcome = build_dbt_execution_outcome(
        plan=plan,
        graph=graph,
        node_results=(
            DbtNodeExecutionResult(
                unique_id="model.analytics.run_me",
                resource_type="model",
                node_name="run_me",
                status="success",
                index=1,
                total=2,
                execution_time=0.1,
            ),
            DbtNodeExecutionResult(
                unique_id="model.analytics.failed",
                resource_type="model",
                node_name="failed",
                status="error",
                index=2,
                total=2,
                execution_time=0.1,
            ),
        ),
    )

    assert tuple((entry.unique_id, entry.state) for entry in outcome.entries) == (
        test_case.expected_states_by_unique_id
    )
    assert outcome.stale_sqlbuild_model_names == test_case.expected_stale_sqlbuild_model_names
    assert outcome.blocked_sqlbuild_model_names == test_case.expected_blocked_sqlbuild_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionOutcomeTestCase(
            description="run results fallback captures failed model omitted from event stream",
            expected_states_by_unique_id=(
                ("model.analytics.failed", DbtModelOutcomeState.BLOCKING),
            ),
            expected_stale_sqlbuild_model_names=(),
            expected_blocked_sqlbuild_model_names=("downstream_failed",),
            expected_output_fragments=(
                "model     failed",
                "FAIL",
                "Database Error in model failed",
            ),
        )
    ],
    ids=["run results fallback captures failed model omitted from event stream"],
)
def test_given_dbt_run_results_when_event_stream_omits_failed_model_then_outcome_blocks_downstream(
    test_case: DbtExecutionOutcomeTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubProcess:
        stdout: None = None

        def wait(self) -> int:
            return 1

    target_path: Path = tmp_path / "target"
    target_path.mkdir()
    (target_path / "run_results.json").write_text(
        '{"results":[{"unique_id":"model.analytics.failed","status":"error",'
        '"execution_time":0.1,"message":"Database Error in model failed"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: StubProcess(),
    )
    project: CompiledProject = build_compiled_project_with_models(
        {"downstream_failed": 'select * from __dbt_ref("failed")'}
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.failed",
                    package_name="analytics",
                    name="failed",
                ),
            )
        )
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    plan: DbtInteropPlan = DbtInteropPlan(
        command=DbtInteropCommand.BUILD,
        dbt_command_argv=("dbt", "build"),
        dbt_selected_nodes=(),
        dbt_selected_unique_ids=(),
        sqlbuild_command_argvs=(),
        selection=DbtInteropSelectionResult(),
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                DbtModelPlanEntry(
                    unique_id="model.analytics.failed",
                    package_name="analytics",
                    name="failed",
                    action=DbtModelPlanAction.RUN,
                    reason=DbtModelPlanReason.CHECKSUM_CHANGED,
                    relation_name="main.failed",
                ),
            )
        ),
    )

    stdout_stream: io.StringIO = io.StringIO()
    result: DbtCommandExecutionResult = execute_dbt_commands(
        runner=DbtRunner(
            invoker=RecordingDbtInvoker(DbtCommandResult(argv=("dbt", "build"), returncode=1))
        ),
        options=DbtCliOptions(target_path=target_path),
        merged_argv=("dbt", "build"),
        progress_stream=io.StringIO(),
        stdout_stream=stdout_stream,
        stderr_stream=io.StringIO(),
        use_color=False,
    )
    outcome: DbtExecutionOutcome = build_dbt_execution_outcome(
        plan=plan,
        graph=graph,
        node_results=result.node_results,
    )

    assert result.returncode == 1
    assert tuple((entry.unique_id, entry.state) for entry in outcome.entries) == (
        test_case.expected_states_by_unique_id
    )
    assert outcome.blocked_sqlbuild_model_names == test_case.expected_blocked_sqlbuild_model_names
    output: str = stdout_stream.getvalue()
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtRunResultsFallbackRenderTestCase(
            description="run results fallback renders failed dbt test detail",
            unique_id="test.analytics.assert_total_revenue",
            status="fail",
            message="Failure in test assert_total_revenue",
            expected_output_fragments=(
                "test      assert_total_revenue",
                "FAIL",
                "Failure in test assert_total_revenue",
            ),
        )
    ],
    ids=["run results fallback renders failed dbt test detail"],
)
def test_given_dbt_run_results_when_event_stream_omits_failed_test_then_renders_failure(
    test_case: DbtRunResultsFallbackRenderTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubProcess:
        stdout: None = None

        def wait(self) -> int:
            return 1

    target_path: Path = tmp_path / "target"
    target_path.mkdir()
    (target_path / "run_results.json").write_text(
        '{"results":[{"unique_id":"'
        + test_case.unique_id
        + '","status":"'
        + test_case.status
        + '","execution_time":0.1,"message":"'
        + test_case.message
        + '"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: StubProcess(),
    )
    stdout_stream: io.StringIO = io.StringIO()

    result: DbtCommandExecutionResult = execute_dbt_commands(
        runner=DbtRunner(
            invoker=RecordingDbtInvoker(DbtCommandResult(argv=("dbt", "test"), returncode=1))
        ),
        options=DbtCliOptions(target_path=target_path),
        merged_argv=("dbt", "test"),
        progress_stream=io.StringIO(),
        stdout_stream=stdout_stream,
        stderr_stream=io.StringIO(),
        use_color=False,
    )

    assert result.returncode == 1
    assert tuple(node.unique_id for node in result.node_results) == (test_case.unique_id,)
    output: str = stdout_stream.getvalue()
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtExecutionTotalRenderTestCase(
            description="dbt ls total overrides inconsistent dbt event counters",
            expected_output_fragments=("  1/2   model", "  2/2   test"),
            unexpected_output_fragments=("2/7", "1/6"),
        )
    ],
    ids=["dbt ls total overrides inconsistent dbt event counters"],
)
def test_given_dbt_execution_when_ls_counts_final_selection_then_streams_consistent_total(
    test_case: DbtExecutionTotalRenderTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubProcess:
        stdout: io.StringIO = io.StringIO(
            '{"data":{"execution_time":0.1,"index":2,"total":7,"status":"OK",'
            '"node_info":{"node_name":"orders","resource_type":"model",'
            '"unique_id":"model.analytics.orders"}},'
            '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n'
            '{"data":{"execution_time":0.1,"index":1,"num_models":6,"status":"pass",'
            '"node_info":{"node_name":"orders_check","resource_type":"test",'
            '"unique_id":"test.analytics.orders_check"}},'
            '"info":{"level":"info","name":"LogTestResult","msg":"PASS"}}\n'
        )

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt.helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: StubProcess(),
    )
    runner: DbtRunner = DbtRunner(
        invoker=MappingDbtInvoker(
            {
                ("dbt", "ls", "--output", "json", "--select", "orders"): DbtCommandResult(
                    argv=("dbt", "ls", "--output", "json", "--select", "orders"),
                    returncode=0,
                    stdout=(
                        '{"unique_id":"model.analytics.orders","resource_type":"model"}\n'
                        '{"unique_id":"test.analytics.orders_check",'
                        '"resource_type":"test"}\n'
                    ),
                )
            }
        )
    )
    stdout_stream: io.StringIO = io.StringIO()

    result: DbtCommandExecutionResult = execute_dbt_commands(
        runner=runner,
        options=DbtCliOptions(),
        merged_argv=("dbt", "build", "--select", "orders"),
        progress_stream=io.StringIO(),
        stdout_stream=stdout_stream,
        stderr_stream=io.StringIO(),
        use_color=False,
    )

    assert result.returncode == 0
    output: str = stdout_stream.getvalue()
    for expected_fragment in test_case.expected_output_fragments:
        assert expected_fragment in output
    for unexpected_fragment in test_case.unexpected_output_fragments:
        assert unexpected_fragment not in output


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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtModelSourceBlockingTestCase(
            description="changed source freshness reruns downstream dbt and SQLBuild models",
            expected_blocked_unique_ids=(),
            expected_blocked_sqlbuild_model_names=(),
            expected_blocked_source_unique_ids=(),
        )
    ],
    ids=["changed source freshness reruns downstream dbt and SQLBuild models"],
)
def test_given_dbt_source_data_version_changed_when_planning_then_runs_downstream_models(
    test_case: DbtModelSourceBlockingTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "dbt_source_changed.duckdb")})
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
                    freshness={},
                ),
            ),
        )
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    try:
        write_source_freshness_record(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="main",
            record=SourceFreshnessRecord(
                source_name="source.analytics.raw.orders",
                target_database=None,
                target_schema="main",
                target_name="raw_orders",
                run_id="previous",
                strategy="column",
                value_kind="timestamp",
                data_version="2026-01-01T00:00:00",
                data_version_hash="previous-hash",
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )
        adapter.execute(
            connection,
            "CREATE TABLE main.raw_orders AS SELECT TIMESTAMP '2026-01-02 00:00:00' AS loaded_at",
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
    assert result.stale_sqlbuild_model_names == ("downstream_orders",)
    entries_by_unique_id: dict[str, DbtModelPlanEntry] = {
        entry.unique_id: entry for entry in result.entries
    }
    assert entries_by_unique_id["model.analytics.stg_orders"].action == DbtModelPlanAction.RUN
    assert (
        entries_by_unique_id["model.analytics.stg_orders"].reason
        == DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED
    )
    assert entries_by_unique_id["model.analytics.fact_orders"].action == DbtModelPlanAction.RUN
    assert (
        entries_by_unique_id["model.analytics.fact_orders"].reason
        == DbtModelPlanReason.SOURCE_FRESHNESS_CHANGED
    )
