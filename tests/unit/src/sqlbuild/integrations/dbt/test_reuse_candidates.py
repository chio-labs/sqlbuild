from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import pytest

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import DependencyBaselinePlanEntry
from sqlbuild.integrations.dbt.constants import (
    DBT_MANIFEST_REUSE_CURSOR_KEY,
    DBT_MANIFEST_SQLBUILD_META_KEY,
    DBT_REUSE_METADATA_CURSOR_COLUMN_KEY,
    DBT_REUSE_METADATA_DESTINATION_RELATION_KEY,
    DBT_REUSE_METADATA_EXECUTION_MODE_KEY,
    DBT_REUSE_METADATA_ORIGIN_RELATION_KEY,
    DBT_REUSE_METADATA_REUSE_MODE_KEY,
)
from sqlbuild.integrations.dbt.helpers.graph.core import dbt_model_graph_key
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.reuse.candidates import (
    build_dbt_reuse_planning_result,
    resolve_dbt_reuse_candidates,
    resolve_dbt_reuse_candidates_for_plan,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtModelPlanningResult,
    DbtReuseCandidate,
    DbtReuseCandidateResolution,
    DbtReusePlanEntry,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.pipeline.helpers.dependency_baseline import (
    build_dbt_native_dependency_baseline_entries,
    dependency_baseline_unique_ids,
)
from sqlbuild.integrations.dbt.types import (
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReuseCandidateSkipReason,
    DbtReuseExecutionMode,
    DbtReuseMode,
    DbtReusePlanAction,
    DbtReusePlanReason,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtDefinitionFingerprintTestCase,
    DbtDependencyBaselineScopeTestCase,
    DbtNativeDependencyBaselineConversionTestCase,
    DbtReuseCandidateResolutionTestCase,
    DbtReuseCascadeTestCase,
    DbtReusePlanningTestCase,
    DbtReuseScopeFromPlanTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_dbt_interop_plan_for_reuse_scope,
    build_dbt_model_plan_entry,
    build_manifest_data,
    build_manifest_macro_node,
    build_manifest_model_node,
)

REUSE_CANDIDATE_RESOLUTION_TEST_CASES: tuple[DbtReuseCandidateResolutionTestCase, ...] = (
    DbtReuseCandidateResolutionTestCase(
        description="returns only scoped table candidates",
        scoped_unique_ids=("model.analytics.orders",),
        current_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.orders",
                package_name="analytics",
                name="orders",
                relation_name="dev.orders",
                materialized="table",
                fqn=("analytics", "orders"),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.unrelated",
                package_name="analytics",
                name="unrelated",
                relation_name="dev.unrelated",
                materialized="table",
            ),
        ),
        reuse_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.orders",
                package_name="analytics",
                name="orders",
                relation_name="prod.orders",
                materialized="table",
                fqn=("analytics", "orders"),
            ),
            build_manifest_model_node(
                unique_id="model.analytics.unrelated",
                package_name="analytics",
                name="unrelated",
                relation_name="prod.unrelated",
                materialized="table",
            ),
        ),
        expected_candidate_unique_ids=("model.analytics.orders",),
        expected_candidate_materializations=("table",),
        expected_origin_relation_names=("prod.orders",),
        expected_skipped=(),
    ),
    DbtReuseCandidateResolutionTestCase(
        description="preserves graph-expanded scoped order and dedupes duplicate ids",
        scoped_unique_ids=(
            "model.analytics.stg_orders",
            "model.analytics.fact_orders",
            "model.analytics.stg_orders",
        ),
        current_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name="dev.stg_orders",
                materialized="table",
            ),
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name="dev.fact_orders",
                materialized="incremental",
            ),
        ),
        reuse_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.stg_orders",
                package_name="analytics",
                name="stg_orders",
                relation_name="prod.stg_orders",
                materialized="table",
            ),
            build_manifest_model_node(
                unique_id="model.analytics.fact_orders",
                package_name="analytics",
                name="fact_orders",
                relation_name="prod.fact_orders",
                materialized="incremental",
            ),
        ),
        expected_candidate_unique_ids=(
            "model.analytics.stg_orders",
            "model.analytics.fact_orders",
        ),
        expected_candidate_materializations=("table", "incremental"),
        expected_origin_relation_names=("prod.stg_orders", "prod.fact_orders"),
        expected_skipped=(),
    ),
    DbtReuseCandidateResolutionTestCase(
        description="classifies microbatch incremental as physical candidate",
        scoped_unique_ids=("model.analytics.events",),
        current_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.events",
                package_name="analytics",
                name="events",
                relation_name="dev.events",
                materialized="incremental",
                incremental_strategy="microbatch",
                meta={
                    DBT_MANIFEST_SQLBUILD_META_KEY: {DBT_MANIFEST_REUSE_CURSOR_KEY: "event_time"}
                },
            ),
        ),
        reuse_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.events",
                package_name="analytics",
                name="events",
                relation_name="prod.events",
                materialized="incremental",
                incremental_strategy="microbatch",
            ),
        ),
        expected_candidate_unique_ids=("model.analytics.events",),
        expected_candidate_materializations=("microbatch",),
        expected_origin_relation_names=("prod.events",),
        expected_skipped=(),
        expected_cursor_columns=("event_time",),
    ),
    DbtReuseCandidateResolutionTestCase(
        description="skips missing reuse manifest node",
        scoped_unique_ids=("model.analytics.orders",),
        current_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.orders",
                package_name="analytics",
                name="orders",
                materialized="table",
            ),
        ),
        reuse_nodes=(),
        expected_candidate_unique_ids=(),
        expected_candidate_materializations=(),
        expected_origin_relation_names=(),
        expected_skipped=(
            ("model.analytics.orders", DbtReuseCandidateSkipReason.REUSE_MANIFEST_MISSING),
        ),
    ),
    DbtReuseCandidateResolutionTestCase(
        description="skips missing current manifest node",
        scoped_unique_ids=("model.analytics.orders",),
        current_nodes=(),
        reuse_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.orders",
                package_name="analytics",
                name="orders",
                materialized="table",
            ),
        ),
        expected_candidate_unique_ids=(),
        expected_candidate_materializations=(),
        expected_origin_relation_names=(),
        expected_skipped=(
            ("model.analytics.orders", DbtReuseCandidateSkipReason.CURRENT_MANIFEST_MISSING),
        ),
    ),
    DbtReuseCandidateResolutionTestCase(
        description="skips views ephemeral and unsupported materializations",
        scoped_unique_ids=(
            "model.analytics.orders_view",
            "model.analytics.temp_orders",
            "model.analytics.custom_orders",
        ),
        current_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.orders_view",
                package_name="analytics",
                name="orders_view",
                materialized="view",
            ),
            build_manifest_model_node(
                unique_id="model.analytics.temp_orders",
                package_name="analytics",
                name="temp_orders",
                materialized="ephemeral",
            ),
            build_manifest_model_node(
                unique_id="model.analytics.custom_orders",
                package_name="analytics",
                name="custom_orders",
                materialized="materialized_view",
            ),
        ),
        reuse_nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.orders_view",
                package_name="analytics",
                name="orders_view",
                materialized="view",
            ),
            build_manifest_model_node(
                unique_id="model.analytics.temp_orders",
                package_name="analytics",
                name="temp_orders",
                materialized="ephemeral",
            ),
            build_manifest_model_node(
                unique_id="model.analytics.custom_orders",
                package_name="analytics",
                name="custom_orders",
                materialized="materialized_view",
            ),
        ),
        expected_candidate_unique_ids=(),
        expected_candidate_materializations=(),
        expected_origin_relation_names=(),
        expected_skipped=(
            ("model.analytics.orders_view", DbtReuseCandidateSkipReason.VIEW),
            ("model.analytics.temp_orders", DbtReuseCandidateSkipReason.EPHEMERAL),
            (
                "model.analytics.custom_orders",
                DbtReuseCandidateSkipReason.UNSUPPORTED_MATERIALIZATION,
            ),
        ),
    ),
)

REUSE_SCOPE_FROM_PLAN_TEST_CASES: tuple[DbtReuseScopeFromPlanTestCase, ...] = (
    DbtReuseScopeFromPlanTestCase(
        description="uses dbt selected unique ids for dbt-native selectors",
        dbt_selected_unique_ids=("model.analytics.orders",),
        dbt_required_unique_ids=(),
        dbt_anchor_unique_ids_by_term={},
        expected_candidate_unique_ids=("model.analytics.orders",),
    ),
    DbtReuseScopeFromPlanTestCase(
        description="uses required dbt unique ids for SQLBuild graph selectors",
        dbt_selected_unique_ids=(),
        dbt_required_unique_ids=("model.analytics.stg_orders", "model.analytics.fact_orders"),
        dbt_anchor_unique_ids_by_term={},
        expected_candidate_unique_ids=("model.analytics.stg_orders", "model.analytics.fact_orders"),
    ),
    DbtReuseScopeFromPlanTestCase(
        description="dedupes selected required and anchor unique ids in plan order",
        dbt_selected_unique_ids=("model.analytics.fact_orders",),
        dbt_required_unique_ids=("model.analytics.stg_orders", "model.analytics.fact_orders"),
        dbt_anchor_unique_ids_by_term={
            "state:modified+": ("model.analytics.stg_orders", "model.analytics.dim_dates")
        },
        expected_candidate_unique_ids=(
            "model.analytics.fact_orders",
            "model.analytics.stg_orders",
            "model.analytics.dim_dates",
        ),
    ),
)

REUSE_PLANNING_TEST_CASES: tuple[DbtReusePlanningTestCase, ...] = (
    DbtReusePlanningTestCase(
        description="plans table first run as complete reuse",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.FIRST_RUN,
        expected_action=DbtReusePlanAction.COMPLETE_REUSE,
        expected_reason=DbtReusePlanReason.FINGERPRINT_MISSING,
    ),
    DbtReusePlanningTestCase(
        description="plans table missing relation as complete reuse",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.RELATION_MISSING,
        expected_action=DbtReusePlanAction.COMPLETE_REUSE,
        expected_reason=DbtReusePlanReason.DESTINATION_MISSING,
    ),
    DbtReusePlanningTestCase(
        description="plans table checksum changed as rebuild",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.CHECKSUM_CHANGED,
        expected_action=DbtReusePlanAction.REBUILD,
        expected_reason=DbtReusePlanReason.FINGERPRINT_CHANGED,
    ),
    DbtReusePlanningTestCase(
        description="plans incremental first run as seeded reuse",
        candidate_materialization="incremental",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.FIRST_RUN,
        expected_action=DbtReusePlanAction.SEEDED_REUSE,
        expected_reason=DbtReusePlanReason.FINGERPRINT_MISSING,
    ),
    DbtReusePlanningTestCase(
        description="plans microbatch relation missing as seeded reuse",
        candidate_materialization="microbatch",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.RELATION_MISSING,
        expected_action=DbtReusePlanAction.SEEDED_REUSE,
        expected_reason=DbtReusePlanReason.DESTINATION_MISSING,
    ),
    DbtReusePlanningTestCase(
        description="plans snapshot checksum changed as rebuild",
        candidate_materialization="snapshot",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.CHECKSUM_CHANGED,
        expected_action=DbtReusePlanAction.REBUILD,
        expected_reason=DbtReusePlanReason.FINGERPRINT_CHANGED,
    ),
    DbtReusePlanningTestCase(
        description="plans current destination as current",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.CURRENT,
        dbt_plan_reason=DbtModelPlanReason.NO_CHANGE,
        expected_action=DbtReusePlanAction.CURRENT,
        expected_reason=DbtReusePlanReason.DESTINATION_CURRENT,
    ),
    DbtReusePlanningTestCase(
        description="plans full refresh as rebuild",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.FULL_REFRESH,
        expected_action=DbtReusePlanAction.REBUILD,
        expected_reason=DbtReusePlanReason.FULL_REFRESH,
    ),
    DbtReusePlanningTestCase(
        description="plans blocked dbt model as blocked reuse",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.BLOCKED,
        dbt_plan_reason=DbtModelPlanReason.SOURCE_FRESHNESS_ERROR,
        expected_action=DbtReusePlanAction.BLOCKED,
        expected_reason=DbtReusePlanReason.SOURCE_FRESHNESS_BLOCK,
    ),
    DbtReusePlanningTestCase(
        description="reuses when only reuse origin definition differs",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.FIRST_RUN,
        expected_action=DbtReusePlanAction.COMPLETE_REUSE,
        expected_reason=DbtReusePlanReason.FINGERPRINT_MISSING,
        current_raw_sql="select 111 as amount from prod.raw",
        origin_raw_sql="select 900 as amount from prod.raw",
    ),
    DbtReusePlanningTestCase(
        description="reuses when current definition matches origin",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.FIRST_RUN,
        expected_action=DbtReusePlanAction.COMPLETE_REUSE,
        expected_reason=DbtReusePlanReason.FINGERPRINT_MISSING,
        current_raw_sql="select 900 as amount from prod.raw",
        origin_raw_sql="select 900 as amount from prod.raw",
    ),
)

REUSE_METADATA_PLANNING_TEST_CASES: tuple[DbtReusePlanningTestCase, ...] = (
    DbtReusePlanningTestCase(
        description="keeps current when reuse metadata still matches candidate relations",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.CURRENT,
        dbt_plan_reason=DbtModelPlanReason.NO_CHANGE,
        expected_action=DbtReusePlanAction.CURRENT,
        expected_reason=DbtReusePlanReason.DESTINATION_CURRENT,
    ),
    DbtReusePlanningTestCase(
        description="reuses again when reuse metadata origin relation changed",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.CURRENT,
        dbt_plan_reason=DbtModelPlanReason.NO_CHANGE,
        expected_action=DbtReusePlanAction.COMPLETE_REUSE,
        expected_reason=DbtReusePlanReason.REUSE_METADATA_INVALID,
    ),
    DbtReusePlanningTestCase(
        description="keeps current seeded reuse when cursor metadata still matches",
        candidate_materialization="microbatch",
        dbt_plan_action=DbtModelPlanAction.CURRENT,
        dbt_plan_reason=DbtModelPlanReason.NO_CHANGE,
        expected_action=DbtReusePlanAction.CURRENT,
        expected_reason=DbtReusePlanReason.DESTINATION_CURRENT,
        cursor_column="event_time",
        previous_cursor_column="event_time",
    ),
    DbtReusePlanningTestCase(
        description="reuses seeded model again when cursor metadata changed",
        candidate_materialization="microbatch",
        dbt_plan_action=DbtModelPlanAction.CURRENT,
        dbt_plan_reason=DbtModelPlanReason.NO_CHANGE,
        expected_action=DbtReusePlanAction.SEEDED_REUSE,
        expected_reason=DbtReusePlanReason.REUSE_METADATA_INVALID,
        cursor_column="updated_at",
        previous_cursor_column="event_time",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    REUSE_CANDIDATE_RESOLUTION_TEST_CASES,
    ids=[case.description for case in REUSE_CANDIDATE_RESOLUTION_TEST_CASES],
)
def test_given_scoped_dbt_nodes_when_resolving_reuse_candidates_then_returns_expected_candidates(
    test_case: DbtReuseCandidateResolutionTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.reuse_nodes)
    )

    result: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
        scoped_unique_ids=test_case.scoped_unique_ids,
    )

    assert tuple(candidate.unique_id for candidate in result.candidates) == (
        test_case.expected_candidate_unique_ids
    )
    assert tuple(candidate.materialization for candidate in result.candidates) == (
        test_case.expected_candidate_materializations
    )
    assert tuple(candidate.origin_relation_name for candidate in result.candidates) == (
        test_case.expected_origin_relation_names
    )
    expected_cursor_columns: tuple[str | None, ...] = test_case.expected_cursor_columns or tuple(
        None for _candidate in result.candidates
    )
    assert (
        tuple(candidate.cursor_column for candidate in result.candidates) == expected_cursor_columns
    )
    assert tuple((skip.unique_id, skip.reason) for skip in result.skipped) == (
        test_case.expected_skipped
    )


@pytest.mark.parametrize(
    "test_case",
    REUSE_SCOPE_FROM_PLAN_TEST_CASES,
    ids=[case.description for case in REUSE_SCOPE_FROM_PLAN_TEST_CASES],
)
def test_given_dbt_interop_plan_when_resolving_reuse_candidates_then_uses_plan_scope(
    test_case: DbtReuseScopeFromPlanTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=tuple(
                build_manifest_model_node(
                    unique_id=unique_id,
                    package_name="analytics",
                    name=unique_id.rsplit(".", maxsplit=1)[-1],
                    relation_name=f"dev.{unique_id.rsplit('.', maxsplit=1)[-1]}",
                    materialized="table",
                )
                for unique_id in (
                    *test_case.expected_candidate_unique_ids,
                    "model.analytics.unrelated",
                )
            )
        )
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=tuple(
                build_manifest_model_node(
                    unique_id=unique_id,
                    package_name="analytics",
                    name=unique_id.rsplit(".", maxsplit=1)[-1],
                    relation_name=f"prod.{unique_id.rsplit('.', maxsplit=1)[-1]}",
                    materialized="table",
                )
                for unique_id in (
                    *test_case.expected_candidate_unique_ids,
                    "model.analytics.unrelated",
                )
            )
        )
    )

    result: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates_for_plan(
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
        plan=build_dbt_interop_plan_for_reuse_scope(
            dbt_selected_unique_ids=test_case.dbt_selected_unique_ids,
            dbt_required_unique_ids=test_case.dbt_required_unique_ids,
            dbt_anchor_unique_ids_by_term=test_case.dbt_anchor_unique_ids_by_term,
        ),
    )

    assert tuple(candidate.unique_id for candidate in result.candidates) == (
        test_case.expected_candidate_unique_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDependencyBaselineScopeTestCase(
            description="uses upstream dbt ancestors as dependency baselines",
            dbt_selected_unique_ids=("model.analytics.fact_orders",),
            expected_baseline_unique_ids=(
                "model.analytics.raw_orders",
                "model.analytics.stg_orders",
            ),
        )
    ],
    ids=["uses upstream dbt ancestors as dependency baselines"],
)
def test_given_selected_dbt_model_when_resolving_dependency_baseline_then_includes_upstream_models(
    test_case: DbtDependencyBaselineScopeTestCase,
) -> None:
    raw_orders_key: DbtCombinedGraphKey = dbt_model_graph_key("model.analytics.raw_orders")
    stg_orders_key: DbtCombinedGraphKey = dbt_model_graph_key("model.analytics.stg_orders")
    fact_orders_key: DbtCombinedGraphKey = dbt_model_graph_key("model.analytics.fact_orders")
    graph: DbtCombinedGraph = DbtCombinedGraph(
        nodes=frozenset((raw_orders_key, stg_orders_key, fact_orders_key)),
        upstream_deps={
            raw_orders_key: (),
            stg_orders_key: (raw_orders_key,),
            fact_orders_key: (stg_orders_key,),
        },
        downstream_deps={
            raw_orders_key: (stg_orders_key,),
            stg_orders_key: (fact_orders_key,),
            fact_orders_key: (),
        },
    )
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=tuple(
                build_manifest_model_node(
                    unique_id=unique_id,
                    package_name="analytics",
                    name=unique_id.rsplit(".", maxsplit=1)[-1],
                    relation_name=f"dev.{unique_id.rsplit('.', maxsplit=1)[-1]}",
                    materialized="table",
                )
                for unique_id in (
                    "model.analytics.raw_orders",
                    "model.analytics.stg_orders",
                    "model.analytics.fact_orders",
                )
            )
        )
    )

    result: tuple[str, ...] = dependency_baseline_unique_ids(
        project=cast(CompiledProject, SimpleNamespace(models=())),
        manifest=manifest,
        graph=graph,
        plan=build_dbt_interop_plan_for_reuse_scope(
            dbt_selected_unique_ids=test_case.dbt_selected_unique_ids,
        ),
    )

    assert result == test_case.expected_baseline_unique_ids


@pytest.mark.parametrize(
    "test_case",
    REUSE_PLANNING_TEST_CASES,
    ids=[case.description for case in REUSE_PLANNING_TEST_CASES],
)
def test_given_dbt_reuse_candidate_and_model_plan_when_planning_then_returns_expected_action(
    test_case: DbtReusePlanningTestCase,
) -> None:
    unique_id: str = "model.analytics.orders"
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="dev.orders",
                        raw_code=test_case.current_raw_sql,
                        materialized=(
                            "incremental"
                            if test_case.candidate_materialization == "microbatch"
                            else test_case.candidate_materialization
                        ),
                        incremental_strategy=(
                            "microbatch"
                            if test_case.candidate_materialization == "microbatch"
                            else None
                        ),
                        meta={
                            DBT_MANIFEST_SQLBUILD_META_KEY: {
                                DBT_MANIFEST_REUSE_CURSOR_KEY: test_case.cursor_column
                            }
                        }
                        if test_case.cursor_column is not None
                        else None,
                    ),
                )
            )
        ),
        reuse_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="prod.orders",
                        raw_code=test_case.origin_raw_sql,
                        materialized=(
                            "incremental"
                            if test_case.candidate_materialization == "microbatch"
                            else test_case.candidate_materialization
                        ),
                        incremental_strategy=(
                            "microbatch"
                            if test_case.candidate_materialization == "microbatch"
                            else None
                        ),
                    ),
                )
            )
        ),
        scoped_unique_ids=(unique_id,),
    )

    result: DbtReusePlanningResult = build_dbt_reuse_planning_result(
        candidate_resolution=candidate_resolution,
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                build_dbt_model_plan_entry(
                    unique_id=unique_id,
                    action=test_case.dbt_plan_action,
                    reason=test_case.dbt_plan_reason,
                ),
            )
        ),
    )

    assert tuple(entry.action for entry in result.entries) == (test_case.expected_action,)
    assert tuple(entry.reason for entry in result.entries) == (test_case.expected_reason,)
    assert result.entries[0].materialization == test_case.candidate_materialization
    assert result.entries[0].cursor_column == test_case.cursor_column


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReusePlanningTestCase(
            description="strict reuse rebuilds when reuse origin definition differs",
            candidate_materialization="table",
            dbt_plan_action=DbtModelPlanAction.RUN,
            dbt_plan_reason=DbtModelPlanReason.FIRST_RUN,
            expected_action=DbtReusePlanAction.REBUILD,
            expected_reason=DbtReusePlanReason.DEFINITION_CHANGED,
            current_raw_sql="select 111 as amount from prod.raw",
            origin_raw_sql="select 900 as amount from prod.raw",
        )
    ],
    ids=["strict reuse rebuilds when reuse origin definition differs"],
)
def test_given_strict_dbt_reuse_when_origin_definition_differs_then_model_rebuilds(
    test_case: DbtReusePlanningTestCase,
) -> None:
    unique_id: str = "model.analytics.orders"
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="dev.orders",
                        raw_code=test_case.current_raw_sql,
                        materialized=test_case.candidate_materialization,
                    ),
                )
            )
        ),
        reuse_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="prod.orders",
                        raw_code=test_case.origin_raw_sql,
                        materialized=test_case.candidate_materialization,
                    ),
                )
            )
        ),
        scoped_unique_ids=(unique_id,),
    )

    result: DbtReusePlanningResult = build_dbt_reuse_planning_result(
        candidate_resolution=candidate_resolution,
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                build_dbt_model_plan_entry(
                    unique_id=unique_id,
                    action=test_case.dbt_plan_action,
                    reason=test_case.dbt_plan_reason,
                ),
            )
        ),
        strict=True,
    )

    assert tuple(entry.action for entry in result.entries) == (test_case.expected_action,)
    assert tuple(entry.reason for entry in result.entries) == (test_case.expected_reason,)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReusePlanningTestCase(
            description="trusted input reuses current project affected dbt input",
            candidate_materialization="table",
            dbt_plan_action=DbtModelPlanAction.RUN,
            dbt_plan_reason=DbtModelPlanReason.CHECKSUM_CHANGED,
            expected_action=DbtReusePlanAction.COMPLETE_REUSE,
            expected_reason=DbtReusePlanReason.FINGERPRINT_CHANGED,
        )
    ],
    ids=["trusted input reuses current project affected dbt input"],
)
def test_given_trusted_dbt_input_when_current_project_affected_then_input_is_reused(
    test_case: DbtReusePlanningTestCase,
) -> None:
    unique_id: str = "model.analytics.orders"
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="dev.orders",
                        materialized=test_case.candidate_materialization,
                    ),
                )
            )
        ),
        reuse_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="prod.orders",
                        materialized=test_case.candidate_materialization,
                    ),
                )
            )
        ),
        scoped_unique_ids=(unique_id,),
    )

    result: DbtReusePlanningResult = build_dbt_reuse_planning_result(
        candidate_resolution=candidate_resolution,
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                build_dbt_model_plan_entry(
                    unique_id=unique_id,
                    action=test_case.dbt_plan_action,
                    reason=test_case.dbt_plan_reason,
                ),
            )
        ),
        trust_reuse_inputs=True,
        current_project_affected_unique_ids=frozenset({unique_id}),
        trusted_input_unique_ids=frozenset({unique_id}),
    )

    assert tuple(entry.action for entry in result.entries) == (test_case.expected_action,)
    assert tuple(entry.reason for entry in result.entries) == (test_case.expected_reason,)
    assert result.entries[0].trusted_input is True
    assert result.entries[0].current_project_affected is True


@pytest.mark.parametrize(
    "test_case",
    [
        DbtNativeDependencyBaselineConversionTestCase(
            description="converts dbt reuse entry to native dependency baseline entry",
            expected_name="model.analytics.fact_orders",
            expected_destination_relation='"dev_db"."main"."fact_orders"',
            expected_origin_relation='"prod_db"."prod"."fact_orders"',
            expected_resource_label="incremental",
            expected_hard_copy=True,
        )
    ],
    ids=["converts dbt reuse entry to native dependency baseline entry"],
)
def test_given_dbt_dependency_baseline_plan_when_converting_then_returns_native_entries(
    test_case: DbtNativeDependencyBaselineConversionTestCase,
) -> None:
    plan: DbtReusePlanningResult = DbtReusePlanningResult(
        entries=(
            DbtReusePlanEntry(
                unique_id=test_case.expected_name,
                action=DbtReusePlanAction.SEEDED_REUSE,
                reason=DbtReusePlanReason.FINGERPRINT_MISSING,
                materialization=test_case.expected_resource_label,
                destination_relation_name=test_case.expected_destination_relation,
                origin_relation_name=test_case.expected_origin_relation,
                trusted_input=True,
                current_project_affected=True,
            ),
        )
    )

    entries: tuple[DependencyBaselinePlanEntry, ...] = build_dbt_native_dependency_baseline_entries(
        plan=plan,
        destination_target_name="dev",
    )

    assert len(entries) == 1
    entry: DependencyBaselinePlanEntry = entries[0]
    assert entry.name == test_case.expected_name
    assert entry.destination.qualified_name == test_case.expected_destination_relation
    assert entry.relation_reuse.origin.qualified_name == test_case.expected_origin_relation
    assert entry.resource_label == test_case.expected_resource_label
    assert entry.relation_reuse.hard_copy == test_case.expected_hard_copy
    assert entry.fingerprint_version_hash is None
    assert entry.trusted_input is True
    assert entry.current_project_affected is True


@pytest.mark.parametrize(
    "test_case",
    REUSE_METADATA_PLANNING_TEST_CASES,
    ids=[case.description for case in REUSE_METADATA_PLANNING_TEST_CASES],
)
def test_given_current_reuse_fingerprint_metadata_when_planning_then_validates_resume_state(
    test_case: DbtReusePlanningTestCase,
) -> None:
    unique_id: str = "model.analytics.orders"
    origin_relation_name: str = (
        "other.orders"
        if test_case.expected_reason == DbtReusePlanReason.REUSE_METADATA_INVALID
        else "prod.orders"
    )
    materialized: str = (
        "incremental"
        if test_case.candidate_materialization == "microbatch"
        else test_case.candidate_materialization
    )
    incremental_strategy: str | None = (
        "microbatch" if test_case.candidate_materialization == "microbatch" else None
    )
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="dev.orders",
                        materialized=materialized,
                        incremental_strategy=incremental_strategy,
                        meta={
                            DBT_MANIFEST_SQLBUILD_META_KEY: {
                                DBT_MANIFEST_REUSE_CURSOR_KEY: test_case.cursor_column
                            }
                        }
                        if test_case.cursor_column is not None
                        else None,
                    ),
                )
            )
        ),
        reuse_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="prod.orders",
                        materialized=materialized,
                        incremental_strategy=incremental_strategy,
                    ),
                )
            )
        ),
        scoped_unique_ids=(unique_id,),
    )

    result: DbtReusePlanningResult = build_dbt_reuse_planning_result(
        candidate_resolution=candidate_resolution,
        dbt_model_plan=DbtModelPlanningResult(
            entries=(
                build_dbt_model_plan_entry(
                    unique_id=unique_id,
                    action=test_case.dbt_plan_action,
                    reason=test_case.dbt_plan_reason,
                    previous_metadata_json=json.dumps(
                        {
                            DBT_REUSE_METADATA_EXECUTION_MODE_KEY: DbtReuseExecutionMode.REUSE,
                            DBT_REUSE_METADATA_REUSE_MODE_KEY: (
                                DbtReuseMode.COMPLETE
                                if test_case.candidate_materialization == "table"
                                else DbtReuseMode.SEEDED
                            ),
                            DBT_REUSE_METADATA_ORIGIN_RELATION_KEY: origin_relation_name,
                            DBT_REUSE_METADATA_DESTINATION_RELATION_KEY: "dev.orders",
                            **(
                                {
                                    DBT_REUSE_METADATA_CURSOR_COLUMN_KEY: (
                                        test_case.previous_cursor_column
                                    )
                                }
                                if test_case.previous_cursor_column is not None
                                else {}
                            ),
                        }
                    ),
                ),
            )
        ),
    )

    assert tuple(entry.action for entry in result.entries) == (test_case.expected_action,)
    assert tuple(entry.reason for entry in result.entries) == (test_case.expected_reason,)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseCandidateResolutionTestCase(
            description="plans skipped view as skipped non physical resource",
            scoped_unique_ids=("model.analytics.orders_view",),
            current_nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders_view",
                    package_name="analytics",
                    name="orders_view",
                    materialized="view",
                ),
            ),
            reuse_nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders_view",
                    package_name="analytics",
                    name="orders_view",
                    materialized="view",
                ),
            ),
            expected_candidate_unique_ids=(),
            expected_candidate_materializations=(),
            expected_origin_relation_names=(),
            expected_skipped=(("model.analytics.orders_view", DbtReuseCandidateSkipReason.VIEW),),
        )
    ],
    ids=["plans skipped view as skipped non physical resource"],
)
def test_given_skipped_reuse_candidate_when_planning_then_returns_skipped_entry(
    test_case: DbtReuseCandidateResolutionTestCase,
) -> None:
    candidate_resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(nodes=test_case.current_nodes)
        ),
        reuse_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(nodes=test_case.reuse_nodes)
        ),
        scoped_unique_ids=test_case.scoped_unique_ids,
    )

    result: DbtReusePlanningResult = build_dbt_reuse_planning_result(
        candidate_resolution=candidate_resolution,
        dbt_model_plan=DbtModelPlanningResult(),
    )

    assert tuple(entry.unique_id for entry in result.entries) == tuple(
        unique_id for unique_id, _reason in test_case.expected_skipped
    )
    assert tuple(entry.action for entry in result.entries) == (DbtReusePlanAction.SKIPPED,)
    assert tuple(entry.reason for entry in result.entries) == (
        DbtReusePlanReason.NON_PHYSICAL_RESOURCE,
    )
    assert tuple(entry.skip_reason for entry in result.entries) == tuple(
        reason for _unique_id, reason in test_case.expected_skipped
    )


REUSE_CASCADE_TEST_CASES: tuple[DbtReuseCascadeTestCase, ...] = (
    DbtReuseCascadeTestCase(
        description="unchanged downstream is upstream-changed when upstream differs",
        upstream_current_raw_sql="select 111 as amount from prod.raw",
        upstream_reuse_raw_sql="select 900 as amount from prod.raw",
        downstream_current_raw_sql="select amount from prod.stg_orders",
        downstream_reuse_raw_sql="select amount from prod.stg_orders",
        expected_downstream_definition_changed=True,
    ),
    DbtReuseCascadeTestCase(
        description="unchanged downstream stays reusable when upstream matches",
        upstream_current_raw_sql="select 900 as amount from prod.raw",
        upstream_reuse_raw_sql="select 900 as amount from prod.raw",
        downstream_current_raw_sql="select amount from prod.stg_orders",
        downstream_reuse_raw_sql="select amount from prod.stg_orders",
        expected_downstream_definition_changed=False,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    REUSE_CASCADE_TEST_CASES,
    ids=[case.description for case in REUSE_CASCADE_TEST_CASES],
)
def test_given_upstream_change_when_resolving_candidates_then_cascades_to_downstream(
    test_case: DbtReuseCascadeTestCase,
) -> None:
    upstream_unique_id: str = "model.analytics.stg_orders"
    downstream_unique_id: str = "model.analytics.fct_orders"
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id=upstream_unique_id,
                    package_name="analytics",
                    name="stg_orders",
                    relation_name="dev.stg_orders",
                    materialized="table",
                    raw_code=test_case.upstream_current_raw_sql,
                ),
                build_manifest_model_node(
                    unique_id=downstream_unique_id,
                    package_name="analytics",
                    name="fct_orders",
                    relation_name="dev.fct_orders",
                    materialized="table",
                    raw_code=test_case.downstream_current_raw_sql,
                    depends_on_nodes=(upstream_unique_id,),
                ),
            )
        )
    )
    reuse_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id=upstream_unique_id,
                    package_name="analytics",
                    name="stg_orders",
                    relation_name="prod.stg_orders",
                    materialized="table",
                    raw_code=test_case.upstream_reuse_raw_sql,
                ),
                build_manifest_model_node(
                    unique_id=downstream_unique_id,
                    package_name="analytics",
                    name="fct_orders",
                    relation_name="prod.fct_orders",
                    materialized="table",
                    raw_code=test_case.downstream_reuse_raw_sql,
                    depends_on_nodes=(upstream_unique_id,),
                ),
            )
        )
    )

    resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=current_manifest,
        reuse_manifest=reuse_manifest,
        scoped_unique_ids=(upstream_unique_id, downstream_unique_id),
    )

    downstream_candidate: DbtReuseCandidate = next(
        candidate
        for candidate in resolution.candidates
        if candidate.unique_id == downstream_unique_id
    )
    assert (
        downstream_candidate.definition_changed_from_origin
        == test_case.expected_downstream_definition_changed
    )


DEFINITION_FINGERPRINT_TEST_CASES: tuple[DbtDefinitionFingerprintTestCase, ...] = (
    DbtDefinitionFingerprintTestCase(
        description="env-only target_schema change does not change the definition",
        current_raw_code="{{ config(target_schema='main') }}\nselect 1 as id",
        origin_raw_code="{{ config(target_schema='prod') }}\nselect 1 as id",
        current_config_overrides={"target_schema": "main"},
        origin_config_overrides={"target_schema": "prod"},
        current_macro_ids=(),
        origin_macro_ids=(),
        current_macro_sql_by_id={},
        origin_macro_sql_by_id={},
        macro_deps_by_id={},
        expected_definition_changed=False,
    ),
    DbtDefinitionFingerprintTestCase(
        description="logical unique_key config change changes the definition",
        current_raw_code="select 1 as id",
        origin_raw_code="select 1 as id",
        current_config_overrides={"unique_key": "order_id"},
        origin_config_overrides={"unique_key": "customer_id"},
        current_macro_ids=(),
        origin_macro_ids=(),
        current_macro_sql_by_id={},
        origin_macro_sql_by_id={},
        macro_deps_by_id={},
        expected_definition_changed=True,
    ),
    DbtDefinitionFingerprintTestCase(
        description="changed macro body changes the definition with unchanged call site",
        current_raw_code="select {{ to_cents('amount') }} as cents",
        origin_raw_code="select {{ to_cents('amount') }} as cents",
        current_config_overrides={},
        origin_config_overrides={},
        current_macro_ids=("macro.analytics.to_cents",),
        origin_macro_ids=("macro.analytics.to_cents",),
        current_macro_sql_by_id={
            "macro.analytics.to_cents": "{% macro to_cents(c) %}{{ c }} * 100{% endmacro %}"
        },
        origin_macro_sql_by_id={
            "macro.analytics.to_cents": "{% macro to_cents(c) %}{{ c }} * 1000{% endmacro %}"
        },
        macro_deps_by_id={},
        expected_definition_changed=True,
    ),
    DbtDefinitionFingerprintTestCase(
        description="changed nested macro body changes the definition transitively",
        current_raw_code="select {{ to_cents('amount') }} as cents",
        origin_raw_code="select {{ to_cents('amount') }} as cents",
        current_macro_ids=("macro.analytics.to_cents",),
        origin_macro_ids=("macro.analytics.to_cents",),
        current_config_overrides={},
        origin_config_overrides={},
        current_macro_sql_by_id={
            "macro.analytics.to_cents": "{% macro to_cents(c) %}{{ inner(c) }}{% endmacro %}",
            "macro.analytics.inner": "{% macro inner(c) %}{{ c }} * 100{% endmacro %}",
        },
        origin_macro_sql_by_id={
            "macro.analytics.to_cents": "{% macro to_cents(c) %}{{ inner(c) }}{% endmacro %}",
            "macro.analytics.inner": "{% macro inner(c) %}{{ c }} * 1000{% endmacro %}",
        },
        macro_deps_by_id={"macro.analytics.to_cents": ("macro.analytics.inner",)},
        expected_definition_changed=True,
    ),
    DbtDefinitionFingerprintTestCase(
        description="identical raw code config and macros leave the definition unchanged",
        current_raw_code="select {{ to_cents('amount') }} as cents",
        origin_raw_code="select {{ to_cents('amount') }} as cents",
        current_macro_ids=("macro.analytics.to_cents",),
        origin_macro_ids=("macro.analytics.to_cents",),
        current_config_overrides={"unique_key": "order_id"},
        origin_config_overrides={"unique_key": "order_id"},
        current_macro_sql_by_id={
            "macro.analytics.to_cents": "{% macro to_cents(c) %}{{ c }} * 100{% endmacro %}"
        },
        origin_macro_sql_by_id={
            "macro.analytics.to_cents": "{% macro to_cents(c) %}{{ c }} * 100{% endmacro %}"
        },
        macro_deps_by_id={},
        expected_definition_changed=False,
    ),
    DbtDefinitionFingerprintTestCase(
        description="generated snapshot wrapper macro change does not change the definition",
        current_raw_code="{{ snapshot_orders_snapshot() }}",
        origin_raw_code="{{ snapshot_orders_snapshot() }}",
        current_macro_ids=("snapshot.analytics.snapshot_orders_snapshot",),
        origin_macro_ids=("snapshot.analytics.snapshot_orders_snapshot",),
        current_config_overrides={"strategy": "timestamp"},
        origin_config_overrides={"strategy": "timestamp"},
        current_macro_sql_by_id={
            "snapshot.analytics.snapshot_orders_snapshot": (
                "{% snapshot orders_snapshot %}{{ config(target_schema='main') }}"
                "select 1{% endsnapshot %}"
            )
        },
        origin_macro_sql_by_id={
            "snapshot.analytics.snapshot_orders_snapshot": (
                "{% snapshot orders_snapshot %}{{ config(target_schema='prod') }}"
                "select 1{% endsnapshot %}"
            )
        },
        macro_deps_by_id={},
        expected_definition_changed=False,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    DEFINITION_FINGERPRINT_TEST_CASES,
    ids=[case.description for case in DEFINITION_FINGERPRINT_TEST_CASES],
)
def test_given_dbt_node_changes_when_resolving_candidates_then_detects_definition_change(
    test_case: DbtDefinitionFingerprintTestCase,
) -> None:
    unique_id: str = "model.analytics.orders"
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id=unique_id,
                    package_name="analytics",
                    name="orders",
                    relation_name="dev.orders",
                    materialized="table",
                    raw_code=test_case.current_raw_code,
                    depends_on_macro_ids=test_case.current_macro_ids,
                    config_overrides=test_case.current_config_overrides,
                ),
            ),
            macros=tuple(
                build_manifest_macro_node(
                    unique_id=macro_id,
                    macro_sql=macro_sql,
                    depends_on_macro_ids=test_case.macro_deps_by_id.get(macro_id, ()),
                )
                for macro_id, macro_sql in test_case.current_macro_sql_by_id.items()
            ),
        )
    )
    origin_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id=unique_id,
                    package_name="analytics",
                    name="orders",
                    relation_name="prod.orders",
                    materialized="table",
                    raw_code=test_case.origin_raw_code,
                    depends_on_macro_ids=test_case.origin_macro_ids,
                    config_overrides=test_case.origin_config_overrides,
                ),
            ),
            macros=tuple(
                build_manifest_macro_node(
                    unique_id=macro_id,
                    macro_sql=macro_sql,
                    depends_on_macro_ids=test_case.macro_deps_by_id.get(macro_id, ()),
                )
                for macro_id, macro_sql in test_case.origin_macro_sql_by_id.items()
            ),
        )
    )

    resolution: DbtReuseCandidateResolution = resolve_dbt_reuse_candidates(
        current_manifest=current_manifest,
        reuse_manifest=origin_manifest,
        scoped_unique_ids=(unique_id,),
    )

    candidate: DbtReuseCandidate = next(
        entry for entry in resolution.candidates if entry.unique_id == unique_id
    )
    assert candidate.definition_changed_from_origin == test_case.expected_definition_changed
