from __future__ import annotations

import json
from typing import cast

import pytest

from sqlbuild.integrations.dbt.helpers.plan import (
    build_dbt_interop_plan,
    format_dbt_interop_plan,
    format_dbt_interop_plan_json,
)
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult, DbtLsNode
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtPlanTestCase

PLAN_TEST_CASES: list[DbtPlanTestCase] = [
    DbtPlanTestCase(
        description="formats mixed dbt and SQLBuild work",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "tag:nightly"),
        dbt_ls_unique_ids=("model.analytics.int_orders",),
        sqlbuild_command_argvs=(("sqb", "run", "--select", "fact_orders"),),
        selection_sqlbuild_model_names=("fact_orders", "mart_orders"),
        selection_dbt_required_unique_ids=(),
        selection_dbt_anchor_terms=(),
        selection_dbt_anchor_unique_ids_by_term={},
        selection_path_translations=(),
        warnings=(),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
        expected_human_fragments=(
            "Plan ready (3 selected)",
            "dbt",
            "command: dbt run --select tag:nightly",
            "SQLBuild",
            "fact_orders",
            "mart_orders",
        ),
        expected_json_fragments=(
            '"command": "run"',
            '"selected_unique_ids": [',
            '"model.analytics.int_orders"',
            '"selected_models": [',
            '"fact_orders"',
        ),
    ),
    DbtPlanTestCase(
        description="skips dbt for SQLBuild-only work",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "local_only"),
        dbt_ls_unique_ids=(),
        sqlbuild_command_argvs=(("sqb", "run", "--select", "local_only"),),
        selection_sqlbuild_model_names=("local_only",),
        selection_dbt_required_unique_ids=(),
        selection_dbt_anchor_terms=(),
        selection_dbt_anchor_unique_ids_by_term={},
        selection_path_translations=(),
        warnings=(),
        expected_dbt_skipped=True,
        expected_sqlbuild_skipped=False,
        expected_human_fragments=(
            "Plan ready (1 selected)",
            "skipped: no dbt work selected",
            "local_only",
        ),
        expected_json_fragments=(
            '"skip_reason": "no_dbt_work"',
            '"selected_models": [',
            '"local_only"',
        ),
    ),
    DbtPlanTestCase(
        description="skips SQLBuild for dbt-only work",
        command="build",
        dbt_command_argv=("dbt", "build", "--select", "state:modified"),
        dbt_ls_unique_ids=("model.analytics.stg_orders",),
        sqlbuild_command_argvs=(),
        selection_sqlbuild_model_names=(),
        selection_dbt_required_unique_ids=(),
        selection_dbt_anchor_terms=(),
        selection_dbt_anchor_unique_ids_by_term={},
        selection_path_translations=(),
        warnings=(),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=True,
        expected_human_fragments=(
            "Plan ready (1 selected)",
            "command: dbt build --select state:modified",
            "skipped: no SQLBuild work selected",
        ),
        expected_json_fragments=(
            '"command": "build"',
            '"skip_reason": "no_sqlbuild_work"',
            '"model.analytics.stg_orders"',
        ),
    ),
    DbtPlanTestCase(
        description="counts required dbt upstreams for SQLBuild-owned selectors",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "model.analytics.int_orders"),
        dbt_ls_unique_ids=(),
        sqlbuild_command_argvs=(("sqb", "run", "--select", "fact_orders"),),
        selection_sqlbuild_model_names=("fact_orders",),
        selection_dbt_required_unique_ids=("model.analytics.int_orders",),
        selection_dbt_anchor_terms=(),
        selection_dbt_anchor_unique_ids_by_term={},
        selection_path_translations=(),
        warnings=(),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
        expected_human_fragments=(
            "Plan ready (2 selected)",
            "required: 1",
            "model.analytics.int_orders",
            "fact_orders",
        ),
        expected_json_fragments=(
            '"required_unique_ids": [',
            '"model.analytics.int_orders"',
            '"selected_models": [',
            '"fact_orders"',
        ),
    ),
    DbtPlanTestCase(
        description="formats no-work plan",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "missing"),
        dbt_ls_unique_ids=(),
        sqlbuild_command_argvs=(),
        selection_sqlbuild_model_names=(),
        selection_dbt_required_unique_ids=(),
        selection_dbt_anchor_terms=(),
        selection_dbt_anchor_unique_ids_by_term={},
        selection_path_translations=(),
        warnings=(),
        expected_dbt_skipped=True,
        expected_sqlbuild_skipped=True,
        expected_human_fragments=(
            "Plan ready (0 selected)",
            "skipped: no dbt work selected",
            "skipped: no SQLBuild work selected",
        ),
        expected_json_fragments=(
            '"selected_unique_ids": []',
            '"selected_models": []',
            '"skip_reason": "no_dbt_work"',
            '"skip_reason": "no_sqlbuild_work"',
        ),
    ),
    DbtPlanTestCase(
        description="formats anchors and path translations",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "package:stripe+"),
        dbt_ls_unique_ids=("model.stripe.stg_charges",),
        sqlbuild_command_argvs=(("sqb", "run", "--select", "fact_charges"),),
        selection_sqlbuild_model_names=("fact_charges",),
        selection_dbt_required_unique_ids=("model.stripe.stg_charges",),
        selection_dbt_anchor_terms=("package:stripe+",),
        selection_dbt_anchor_unique_ids_by_term={"package:stripe+": ("model.stripe.stg_charges",)},
        selection_path_translations=(("path:models/marts", "path:marts"),),
        warnings=(),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
        expected_human_fragments=(
            "required: 1",
            "dbt anchors (1)",
            "package:stripe+: 1",
            "Path translations (1)",
            "path:models/marts -> path:marts",
        ),
        expected_json_fragments=(
            '"required_unique_ids": [',
            '"term": "package:stripe+"',
            '"from": "path:models/marts"',
            '"to": "path:marts"',
        ),
    ),
    DbtPlanTestCase(
        description="formats warnings in human and JSON output",
        command="plan",
        dbt_command_argv=("dbt", "ls", "--select", "fact_orders"),
        dbt_ls_unique_ids=(),
        sqlbuild_command_argvs=(("sqb", "plan", "--select", "fact_orders"),),
        selection_sqlbuild_model_names=("fact_orders",),
        selection_dbt_required_unique_ids=(),
        selection_dbt_anchor_terms=(),
        selection_dbt_anchor_unique_ids_by_term={},
        selection_path_translations=(),
        warnings=("dbt options were ignored",),
        expected_dbt_skipped=True,
        expected_sqlbuild_skipped=False,
        expected_human_fragments=(
            "Warnings (1)",
            "- dbt options were ignored",
        ),
        expected_json_fragments=(
            '"warnings": [',
            '"dbt options were ignored"',
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_TEST_CASES,
    ids=[case.description for case in PLAN_TEST_CASES],
)
def test_given_dbt_interop_plan_inputs_when_building_plan_then_formats_expected_output(
    test_case: DbtPlanTestCase,
) -> None:
    selection: DbtInteropSelectionResult = DbtInteropSelectionResult(
        sqlbuild_model_names=test_case.selection_sqlbuild_model_names,
        dbt_required_unique_ids=test_case.selection_dbt_required_unique_ids,
        dbt_anchor_terms=test_case.selection_dbt_anchor_terms,
        dbt_anchor_unique_ids_by_term=test_case.selection_dbt_anchor_unique_ids_by_term,
        path_translations=test_case.selection_path_translations,
    )
    dbt_ls_nodes: tuple[DbtLsNode, ...] = tuple(
        DbtLsNode(unique_id=unique_id) for unique_id in test_case.dbt_ls_unique_ids
    )

    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=test_case.command,
        dbt_command_argv=test_case.dbt_command_argv,
        dbt_ls_nodes=dbt_ls_nodes,
        sqlbuild_command_argvs=test_case.sqlbuild_command_argvs,
        selection=selection,
        warnings=test_case.warnings,
    )
    human_output: str = format_dbt_interop_plan(plan, use_color=False)
    json_output: str = format_dbt_interop_plan_json(plan)
    json_data: dict[str, object] = json.loads(json_output)
    dbt_data: dict[str, object] = cast(dict[str, object], json_data["dbt"])
    sqlbuild_data: dict[str, object] = cast(dict[str, object], json_data["sqlbuild"])

    assert (plan.dbt_skip_reason is not None) == test_case.expected_dbt_skipped
    assert (plan.sqlbuild_skip_reason is not None) == test_case.expected_sqlbuild_skipped
    assert json_data["command"] == test_case.command
    assert dbt_data["supplemental_argvs"] == [
        list(argv) for argv in plan.supplemental_dbt_command_argvs
    ]
    assert dbt_data["selected_unique_ids"] == list(test_case.dbt_ls_unique_ids)
    assert dbt_data["required_unique_ids"] == list(test_case.selection_dbt_required_unique_ids)
    assert dbt_data["required_selector_terms"] == list(plan.dbt_required_selector_terms)
    assert dbt_data["skipped"] == test_case.expected_dbt_skipped
    assert sqlbuild_data["selected_models"] == list(test_case.selection_sqlbuild_model_names)
    assert sqlbuild_data["skipped"] == test_case.expected_sqlbuild_skipped
    assert json_data["anchors"] == [
        {
            "term": term,
            "unique_ids": list(test_case.selection_dbt_anchor_unique_ids_by_term.get(term, ())),
        }
        for term in test_case.selection_dbt_anchor_terms
    ]
    assert json_data["path_translations"] == [
        {"from": original, "to": translated}
        for original, translated in test_case.selection_path_translations
    ]
    assert json_data["warnings"] == list(test_case.warnings)
    for fragment in test_case.expected_human_fragments:
        assert fragment in human_output
    for fragment in test_case.expected_json_fragments:
        assert fragment in json_output
