from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtPlanCliTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    load_json_stdout,
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

PLAN_CLI_TEST_CASES: list[DbtPlanCliTestCase] = [
    DbtPlanCliTestCase(
        description="reports SQLBuild-only selected work and dbt skip",
        command=("dbt", "plan", "--json", "--select", "local_only"),
        expected_selected_models=("local_only",),
        expected_dbt_skipped=True,
        expected_sqlbuild_skipped=False,
    ),
    DbtPlanCliTestCase(
        description="reports dbt trailing plus anchors and downstream SQLBuild work",
        command=("dbt", "plan", "--json", "--select", "fact_orders+"),
        expected_selected_models=("downstream_orders", "mart_orders"),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
        expected_anchor_terms=("fact_orders+",),
    ),
    DbtPlanCliTestCase(
        description="reports dbt path translation for SQLBuild model paths",
        command=("dbt", "plan", "--json", "--select", "path:models/marts"),
        expected_selected_models=("deprecated_orders", "downstream_orders", "mart_orders"),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
        expected_path_translations=(("path:models/marts", "path:marts"),),
    ),
    DbtPlanCliTestCase(
        description="reports mixed dbt and SQLBuild tag matches",
        command=("dbt", "plan", "--json", "--select", "tag:nightly"),
        expected_selected_models=("downstream_orders",),
        expected_dbt_skipped=False,
        expected_sqlbuild_skipped=False,
    ),
    DbtPlanCliTestCase(
        description="reports SQLBuild-only tag matches with dbt skipped",
        command=("dbt", "plan", "--json", "--select", "tag:sqb_only"),
        expected_selected_models=("deprecated_orders", "local_only"),
        expected_dbt_skipped=True,
        expected_sqlbuild_skipped=False,
    ),
    DbtPlanCliTestCase(
        description="reports SQLBuild tag excludes",
        command=(
            "dbt",
            "plan",
            "--json",
            "--select",
            "tag:sqb_only",
            "--exclude",
            "tag:deprecated",
        ),
        expected_selected_models=("local_only",),
        expected_dbt_skipped=True,
        expected_sqlbuild_skipped=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_CLI_TEST_CASES,
    ids=[case.description for case in PLAN_CLI_TEST_CASES],
)
def test_given_dbt_interop_project_when_running_plan_json_then_outputs_expected_plan(
    test_case: DbtPlanCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    dbt_payload: object = payload["dbt"]
    sqlbuild_payload: object = payload["sqlbuild"]
    anchors_payload: object = payload["anchors"]
    path_translations_payload: object = payload["path_translations"]
    assert isinstance(dbt_payload, dict)
    assert isinstance(sqlbuild_payload, dict)
    assert isinstance(anchors_payload, Sequence)
    assert isinstance(path_translations_payload, Sequence)
    typed_dbt_payload: Mapping[str, object] = cast(Mapping[str, object], dbt_payload)
    typed_sqlbuild_payload: Mapping[str, object] = cast(Mapping[str, object], sqlbuild_payload)
    assert typed_sqlbuild_payload["selected_models"] == list(test_case.expected_selected_models)
    assert typed_dbt_payload["skipped"] == test_case.expected_dbt_skipped
    assert typed_sqlbuild_payload["skipped"] == test_case.expected_sqlbuild_skipped
    assert [
        cast(Mapping[str, object], anchor)["term"]
        for anchor in anchors_payload
        if isinstance(anchor, dict)
    ] == list(test_case.expected_anchor_terms)
    assert [
        (
            cast(Mapping[str, object], translation)["from"],
            cast(Mapping[str, object], translation)["to"],
        )
        for translation in path_translations_payload
        if isinstance(translation, dict)
    ] == list(test_case.expected_path_translations)
