from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt._helpers.planning.plan import (
    build_dbt_interop_plan,
    format_dbt_interop_plan,
    format_dbt_interop_plan_json,
)
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult, DbtLsNode
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtPlanTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPlanTestCase(
            description="renders selected and required work without dbt state classifications",
            command="build",
            dbt_command_argv=("dbt", "build", "--select", "orders"),
            dbt_ls_unique_ids=("model.analytics.orders",),
            sqlbuild_command_argvs=(("sqb", "build", "--select", "local_orders"),),
            selection_sqlbuild_model_names=("local_orders",),
            selection_dbt_required_unique_ids=("model.analytics.customers",),
            selection_dbt_anchor_terms=(),
            selection_dbt_anchor_unique_ids_by_term={},
            selection_path_translations=(),
            warnings=(),
            expected_dbt_skipped=False,
            expected_sqlbuild_skipped=False,
            expected_human_fragments=(
                "orders",
                "model.analytics.customers",
                "local_orders",
            ),
            expected_json_fragments=(
                '"selected_unique_ids": [',
                '"required_unique_ids": [',
                '"selected_models": [',
            ),
        ),
        DbtPlanTestCase(
            description="renders clear skips when neither side has work",
            command="plan",
            dbt_command_argv=("dbt", "ls"),
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
            expected_human_fragments=("no dbt work selected", "no SQLBuild work selected"),
            expected_json_fragments=('"skipped": true',),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_interop_selection_when_rendering_then_reports_selected_work_only(
    test_case: DbtPlanTestCase,
) -> None:
    nodes: tuple[DbtLsNode, ...] = tuple(
        DbtLsNode(
            unique_id=unique_id,
            resource_type="model",
            package_name="analytics",
            name=unique_id.rsplit(".", 1)[-1],
        )
        for unique_id in test_case.dbt_ls_unique_ids
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=test_case.command,
        dbt_command_argv=test_case.dbt_command_argv,
        dbt_ls_nodes=nodes,
        sqlbuild_command_argvs=test_case.sqlbuild_command_argvs,
        selection=DbtInteropSelectionResult(
            sqlbuild_model_names=test_case.selection_sqlbuild_model_names,
            dbt_required_unique_ids=test_case.selection_dbt_required_unique_ids,
            dbt_anchor_terms=test_case.selection_dbt_anchor_terms,
            dbt_anchor_unique_ids_by_term=test_case.selection_dbt_anchor_unique_ids_by_term,
            path_translations=test_case.selection_path_translations,
        ),
        warnings=test_case.warnings,
    )

    human: str = format_dbt_interop_plan(plan=plan, use_color=False)
    json_output: str = format_dbt_interop_plan_json(plan)

    assert (plan.dbt_skip_reason is not None) is test_case.expected_dbt_skipped
    assert (plan.sqlbuild_skip_reason is not None) is test_case.expected_sqlbuild_skipped
    for fragment in test_case.expected_human_fragments:
        assert fragment in human
    for fragment in test_case.expected_json_fragments:
        assert fragment in json_output
    assert "model_plan" not in json_output
