from __future__ import annotations

import json
import re
from typing import cast

import pytest

from sqlbuild.integrations.dbt.helpers.plan import (
    build_dbt_interop_plan,
    format_dbt_interop_plan,
    format_dbt_interop_plan_json,
)
from sqlbuild.integrations.dbt.models import DbtInteropPlan, DbtInteropSelectionResult, DbtLsNode
from sqlbuild.shared.helpers.display import DisplayOptions
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtPlanHumanFormatterTestCase,
    DbtPlanTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import build_sqlbuild_plan_output

PLAN_TEST_CASES: list[DbtPlanTestCase] = [
    DbtPlanTestCase(
        description="formats mixed dbt and SQLBuild work",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "tag:nightly"),
        dbt_ls_unique_ids=("model.analytics.int_orders",),
        sqlbuild_command_argvs=(
            ("sqb", "build", "--no-tests", "--no-audits", "--select", "fact_orders"),
        ),
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
        sqlbuild_command_argvs=(
            ("sqb", "build", "--no-tests", "--no-audits", "--select", "local_only"),
        ),
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
        sqlbuild_command_argvs=(
            ("sqb", "build", "--no-tests", "--no-audits", "--select", "fact_orders"),
        ),
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
        description="formats anchors and path normalizations",
        command="run",
        dbt_command_argv=("dbt", "run", "--select", "package:stripe+"),
        dbt_ls_unique_ids=("model.stripe.stg_charges",),
        sqlbuild_command_argvs=(
            ("sqb", "build", "--no-tests", "--no-audits", "--select", "fact_charges"),
        ),
        selection_sqlbuild_model_names=("fact_charges",),
        selection_dbt_required_unique_ids=("model.stripe.stg_charges",),
        selection_dbt_anchor_terms=("package:stripe+",),
        selection_dbt_anchor_unique_ids_by_term={"package:stripe+": ("model.stripe.stg_charges",)},
        selection_path_translations=(("path:models\\marts", "path:models/marts"),),
        warnings=(),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
        expected_human_fragments=(
            "Path translations (1)",
            "path:models\\marts -> path:models/marts",
        ),
        expected_json_fragments=(
            '"required_unique_ids": [',
            '"term": "package:stripe+"',
            '"from": "path:models\\\\marts"',
            '"to": "path:models/marts"',
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

FORMATTER_TEST_CASES: list[DbtPlanHumanFormatterTestCase] = [
    DbtPlanHumanFormatterTestCase(
        description="caps dbt and SQLBuild resource sections with verbose guidance",
        dbt_ls_nodes=tuple(
            DbtLsNode(
                unique_id=f"model.analytics.model_{index}",
                resource_type="model",
                package_name="analytics",
                name=f"model_{index}",
            )
            for index in range(3)
        ),
        sqlbuild_model_names=("local_one", "local_two", "local_three"),
        sqlbuild_plan_model_names=(),
        display_limit=2,
        use_color=False,
        expected_human_fragments=(
            "analytics.model_0",
            "analytics.model_1",
            "local_one",
            "local_two",
            "... and 1 more (use --verbose to show all)",
        ),
        expected_human_regex_fragments=(),
        expected_absent_fragments=("analytics.model_2", "local_three          model"),
    ),
    DbtPlanHumanFormatterTestCase(
        description="groups dbt resources with SQLBuild section styling and dbt names orange",
        dbt_ls_nodes=(
            DbtLsNode(
                unique_id="test.analytics.unique_orders.abc123",
                resource_type="test",
                package_name="analytics",
                name="unique_orders",
            ),
            DbtLsNode(
                unique_id="model.analytics.orders",
                resource_type="model",
                package_name="analytics",
                name="orders",
            ),
        ),
        sqlbuild_model_names=(),
        sqlbuild_plan_model_names=(),
        display_limit=None,
        use_color=True,
        expected_human_fragments=(
            "dbt (2 selected)",
            "Models (1)",
            "Tests (1)",
            "analytics.orders",
            "analytics.unique_orders",
        ),
        expected_human_regex_fragments=(
            r"\x1b\[92mModels \(1\)\x1b\[0m",
            r"\x1b\[92mTests \(1\)\x1b\[0m",
            r"\x1b\[38;5;208m\x1b\[1manalytics\.orders\x1b\[0m",
        ),
        expected_absent_fragments=(),
    ),
    DbtPlanHumanFormatterTestCase(
        description="reuses SQLBuild plan formatter sections when plan output is present",
        dbt_ls_nodes=(),
        sqlbuild_model_names=("downstream_orders",),
        sqlbuild_plan_model_names=("downstream_orders",),
        display_limit=None,
        use_color=False,
        expected_human_fragments=(
            "SQLBuild (1 selected)",
            "command: sqb plan --select downstream_orders",
            "Models (1 standard run)",
            "downstream_orders    table",
        ),
        expected_human_regex_fragments=(),
        expected_absent_fragments=(),
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPlanTestCase(
            description="places dbt anchors before SQLBuild selection",
            command="build",
            dbt_command_argv=("dbt", "build", "--select", "+fct_customer_revenue+"),
            dbt_ls_unique_ids=(),
            sqlbuild_command_argvs=(("sqb", "build", "--select", "customer_revenue_check"),),
            selection_sqlbuild_model_names=("customer_revenue_check",),
            selection_dbt_required_unique_ids=(),
            selection_dbt_anchor_terms=("+fct_customer_revenue+",),
            selection_dbt_anchor_unique_ids_by_term={
                "+fct_customer_revenue+": ("model.analytics.fct_customer_revenue",)
            },
            selection_path_translations=(),
            warnings=(),
            expected_dbt_skipped=False,
            expected_sqlbuild_skipped=False,
            expected_human_fragments=("dbt anchors", "SQLBuild"),
            expected_json_fragments=(),
        )
    ],
    ids=["places dbt anchors before SQLBuild selection"],
)
def test_given_dbt_anchors_when_formatting_human_output_then_anchor_section_precedes_sqlbuild(
    test_case: DbtPlanTestCase,
) -> None:
    selection: DbtInteropSelectionResult = DbtInteropSelectionResult(
        sqlbuild_model_names=test_case.selection_sqlbuild_model_names,
        dbt_anchor_terms=test_case.selection_dbt_anchor_terms,
        dbt_anchor_unique_ids_by_term=test_case.selection_dbt_anchor_unique_ids_by_term,
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command=test_case.command,
        dbt_command_argv=test_case.dbt_command_argv,
        dbt_ls_nodes=(),
        sqlbuild_command_argvs=test_case.sqlbuild_command_argvs,
        selection=selection,
    )

    human_output: str = format_dbt_interop_plan(
        plan,
        use_color=False,
        display_options=DisplayOptions(max_entries_per_section=None),
    )

    for expected_fragment in test_case.expected_human_fragments:
        assert expected_fragment in human_output
    assert human_output.index("dbt anchors") < human_output.index("SQLBuild")


@pytest.mark.parametrize(
    "test_case",
    FORMATTER_TEST_CASES,
    ids=[case.description for case in FORMATTER_TEST_CASES],
)
def test_given_dbt_interop_plan_when_formatting_human_output_then_uses_expected_sections(
    test_case: DbtPlanHumanFormatterTestCase,
) -> None:
    selection: DbtInteropSelectionResult = DbtInteropSelectionResult(
        sqlbuild_model_names=test_case.sqlbuild_model_names
    )
    plan: DbtInteropPlan = build_dbt_interop_plan(
        command="plan",
        dbt_command_argv=("dbt", "ls", "--select", "tag:nightly"),
        dbt_ls_nodes=test_case.dbt_ls_nodes,
        sqlbuild_command_argvs=(("sqb", "plan", "--select", *test_case.sqlbuild_model_names),)
        if test_case.sqlbuild_model_names
        else (),
        selection=selection,
        sqlbuild_plan_output=(
            build_sqlbuild_plan_output(test_case.sqlbuild_plan_model_names)
            if test_case.sqlbuild_plan_model_names
            else None
        ),
    )

    human_output: str = format_dbt_interop_plan(
        plan,
        use_color=test_case.use_color,
        display_options=DisplayOptions(max_entries_per_section=test_case.display_limit),
    )

    for expected_fragment in test_case.expected_human_fragments:
        assert expected_fragment in human_output
    for expected_regex in test_case.expected_human_regex_fragments:
        assert re.search(expected_regex, human_output)
    for absent_fragment in test_case.expected_absent_fragments:
        assert absent_fragment not in human_output
