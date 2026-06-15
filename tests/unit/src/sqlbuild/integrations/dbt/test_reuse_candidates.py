from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.helpers.reuse_candidates import (
    build_dbt_reuse_planning_result,
    resolve_dbt_reuse_candidates,
    resolve_dbt_reuse_candidates_for_plan,
)
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtModelPlanningResult,
    DbtReuseCandidateResolution,
    DbtReusePlanningResult,
)
from sqlbuild.integrations.dbt.types import (
    DbtModelPlanAction,
    DbtModelPlanReason,
    DbtReuseCandidateSkipReason,
    DbtReusePlanAction,
    DbtReusePlanReason,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtReuseCandidateResolutionTestCase,
    DbtReusePlanningTestCase,
    DbtReuseScopeFromPlanTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_dbt_interop_plan_for_reuse_scope,
    build_dbt_model_plan_entry,
    build_manifest_data,
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
        expected_reuse_relation_names=("prod.orders",),
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
        expected_reuse_relation_names=("prod.stg_orders", "prod.fact_orders"),
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
        expected_reuse_relation_names=("prod.events",),
        expected_skipped=(),
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
        expected_reuse_relation_names=(),
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
        expected_reuse_relation_names=(),
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
        expected_reuse_relation_names=(),
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
        expected_reason=DbtReusePlanReason.TARGET_MISSING,
    ),
    DbtReusePlanningTestCase(
        description="plans table checksum changed as complete reuse",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.CHECKSUM_CHANGED,
        expected_action=DbtReusePlanAction.COMPLETE_REUSE,
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
        expected_reason=DbtReusePlanReason.TARGET_MISSING,
    ),
    DbtReusePlanningTestCase(
        description="plans snapshot checksum changed as seeded reuse",
        candidate_materialization="snapshot",
        dbt_plan_action=DbtModelPlanAction.RUN,
        dbt_plan_reason=DbtModelPlanReason.CHECKSUM_CHANGED,
        expected_action=DbtReusePlanAction.SEEDED_REUSE,
        expected_reason=DbtReusePlanReason.FINGERPRINT_CHANGED,
    ),
    DbtReusePlanningTestCase(
        description="plans current target as current",
        candidate_materialization="table",
        dbt_plan_action=DbtModelPlanAction.CURRENT,
        dbt_plan_reason=DbtModelPlanReason.NO_CHANGE,
        expected_action=DbtReusePlanAction.CURRENT,
        expected_reason=DbtReusePlanReason.TARGET_CURRENT,
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
    assert tuple(candidate.reuse_relation_name for candidate in result.candidates) == (
        test_case.expected_reuse_relation_names
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
        reuse_manifest=build_dbt_manifest_index(
            raw_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id=unique_id,
                        package_name="analytics",
                        name="orders",
                        relation_name="prod.orders",
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
            expected_reuse_relation_names=(),
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
