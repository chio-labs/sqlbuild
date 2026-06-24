from __future__ import annotations

import json

import pytest

from sqlbuild.integrations.dbt.helpers.identity_diff.core import (
    build_dbt_identity_diff_result,
    format_dbt_identity_diff_json,
    render_dbt_identity_diff_result,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtIdentityDiffResult
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtIdentityDiffTestCase
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_identity_diff_manifest_model_node,
    build_manifest_data,
)

IDENTITY_DIFF_TEST_CASES: tuple[DbtIdentityDiffTestCase, ...] = (
    DbtIdentityDiffTestCase(
        description="reports would reuse for identical identity",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="same", raw_code="select 1 as order_id"
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="same", raw_code="select 1 as order_id"
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=("WOULD-REUSE", "no identity differences"),
        expected_json_fragments=('"verdict": "would_reuse"',),
    ),
    DbtIdentityDiffTestCase(
        description="reports direct sql cause",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="new", raw_code="select 2 as order_id"
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="old", raw_code="select 1 as order_id"
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=(
            "CAUSE",
            "QUERY",
            "-select 1 as order_id",
            "+select 2 as order_id",
        ),
        expected_json_fragments=('"query"', '"model.analytics.orders"'),
    ),
    DbtIdentityDiffTestCase(
        description="collapses downstream and reports upstream sql cause",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.stg_orders", checksum="new", raw_code="select 2 as order_id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.fact_orders",
                checksum="fact",
                raw_code="select * from stg_orders",
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.stg_orders", checksum="old", raw_code="select 1 as order_id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.fact_orders",
                checksum="fact",
                raw_code="select * from stg_orders",
                depends_on_nodes=("model.analytics.stg_orders",),
            ),
        ),
        selected_unique_ids=("model.analytics.fact_orders",),
        expected_output_fragments=("UPSTREAM only", "stg_orders", "CAUSE", "QUERY"),
        expected_json_fragments=('"upstream_only"', '"query"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports config and schema causes",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders",
                checksum="new",
                raw_code="select 1 as order_id",
                materialized="table",
                columns={"order_id": {"name": "order_id", "data_type": "integer"}},
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.orders",
                checksum="old",
                raw_code="select 1 as order_id",
                materialized="view",
                columns={"order_id": {"name": "order_id", "data_type": "varchar"}},
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=("CONFIG", "SCHEMA", "materialized", "data_type"),
        expected_json_fragments=('"config"', '"schema"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports multiple independent upstream causes",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.left", checksum="left_new", raw_code="select 10 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.right", checksum="right_new", raw_code="select 20 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.joined",
                checksum="joined",
                raw_code="select * from left join right using (id)",
                depends_on_nodes=("model.analytics.left", "model.analytics.right"),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.left", checksum="left_old", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.right", checksum="right_old", raw_code="select 2 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.joined",
                checksum="joined",
                raw_code="select * from left join right using (id)",
                depends_on_nodes=("model.analytics.left", "model.analytics.right"),
            ),
        ),
        selected_unique_ids=("model.analytics.joined",),
        expected_output_fragments=("2 cause(s)", "left", "right"),
        expected_json_fragments=('"model.analytics.left"', '"model.analytics.right"'),
    ),
    DbtIdentityDiffTestCase(
        description="reports upstream set change",
        current_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.base", checksum="base", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.orders",
                checksum="new",
                raw_code="select * from base",
                depends_on_nodes=("model.analytics.base",),
            ),
        ),
        ref_nodes=(
            build_identity_diff_manifest_model_node(
                "model.analytics.base", checksum="base", raw_code="select 1 as id"
            ),
            build_identity_diff_manifest_model_node(
                "model.analytics.orders", checksum="old", raw_code="select * from base"
            ),
        ),
        selected_unique_ids=("model.analytics.orders",),
        expected_output_fragments=("UPSTREAM SET", "+ model.analytics.base"),
        expected_json_fragments=('"upstream_set"', '"model.analytics.base"'),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    IDENTITY_DIFF_TEST_CASES,
    ids=[case.description for case in IDENTITY_DIFF_TEST_CASES],
)
def test_given_current_and_ref_manifests_when_building_identity_diff_then_reports_expected_causes(
    test_case: DbtIdentityDiffTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=False,
        use_color=False,
    )
    rendered_json: str = format_dbt_identity_diff_json(result)
    json.loads(rendered_json)

    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered
    for fragment in test_case.expected_json_fragments:
        assert fragment in rendered_json


@pytest.mark.parametrize(
    "test_case",
    [
        DbtIdentityDiffTestCase(
            description="quiet output suppresses diff bodies",
            current_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.orders", checksum="new", raw_code="select 2 as order_id"
                ),
            ),
            ref_nodes=(
                build_identity_diff_manifest_model_node(
                    "model.analytics.orders", checksum="old", raw_code="select 1 as order_id"
                ),
            ),
            selected_unique_ids=("model.analytics.orders",),
            expected_output_fragments=("CAUSE", "QUERY"),
            expected_json_fragments=(),
        )
    ],
    ids=["quiet output suppresses diff bodies"],
)
def test_given_quiet_identity_diff_when_rendering_then_suppresses_diff_bodies(
    test_case: DbtIdentityDiffTestCase,
) -> None:
    current_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.current_nodes)
    )
    ref_manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(nodes=test_case.ref_nodes)
    )

    result: DbtIdentityDiffResult = build_dbt_identity_diff_result(
        current_manifest=current_manifest,
        ref_manifest=ref_manifest,
        selected_unique_ids=test_case.selected_unique_ids,
        against="main",
    )
    rendered: str = render_dbt_identity_diff_result(
        result=result,
        quiet=True,
        use_color=False,
    )

    for fragment in test_case.expected_output_fragments:
        assert fragment in rendered
    assert "-select 1 as order_id" not in rendered
    assert "+select 2 as order_id" not in rendered
