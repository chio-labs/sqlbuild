"""Direct changes-only selector boundary E2E tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectChangesOnlySelectorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_direct_changes_only_project_toml,
    direct_changes_only_stg_orders_sql,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)

TEST_CASES: list[DirectChangesOnlySelectorE2ETestCase] = [
    DirectChangesOnlySelectorE2ETestCase(
        description="name selector stays on changed upstream",
        selector="stg_orders",
        expected_selected_count=1,
        expected_model_names=("stg_orders",),
        unexpected_model_names=(),
        expected_remaining_stale_names=("fact_orders",),
    ),
    DirectChangesOnlySelectorE2ETestCase(
        description="name downstream expansion includes stale downstream",
        selector="stg_orders+",
        expected_selected_count=2,
        expected_model_names=("stg_orders", "fact_orders"),
        unexpected_model_names=(),
    ),
    DirectChangesOnlySelectorE2ETestCase(
        description="upstream expansion includes changed upstream and downstream",
        selector="+fact_orders",
        expected_selected_count=2,
        expected_model_names=("stg_orders", "fact_orders"),
        unexpected_model_names=(),
    ),
    DirectChangesOnlySelectorE2ETestCase(
        description="tag selector stays inside tagged upstream",
        selector="tag:staging",
        expected_selected_count=1,
        expected_model_names=("stg_orders",),
        unexpected_model_names=(),
        expected_remaining_stale_names=("fact_orders",),
    ),
    DirectChangesOnlySelectorE2ETestCase(
        description="tag downstream expansion includes stale downstream",
        selector="tag:staging+",
        expected_selected_count=2,
        expected_model_names=("stg_orders", "fact_orders"),
        unexpected_model_names=(),
    ),
    DirectChangesOnlySelectorE2ETestCase(
        description="path selector stays inside matched upstream path",
        selector="path:models/staging",
        expected_selected_count=1,
        expected_model_names=("stg_orders",),
        unexpected_model_names=(),
        expected_remaining_stale_names=("fact_orders",),
    ),
    DirectChangesOnlySelectorE2ETestCase(
        description="path downstream expansion includes stale downstream",
        selector="path:models/staging+",
        expected_selected_count=2,
        expected_model_names=("stg_orders", "fact_orders"),
        unexpected_model_names=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_upstream_change_when_planning_with_selector_then_respects_selector_scope(
    test_case: DirectChangesOnlySelectorE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_selector_scope",
        repo_files={
            "sqlbuild_project.toml": build_direct_changes_only_project_toml(
                project_name="direct_changes_only_selector_scope"
            ),
            "models/staging/stg_orders.sql": direct_changes_only_stg_orders_sql(
                amount_cents=100, tags=", tags [staging]"
            ),
            "models/marts/fact_orders.sql": (
                "MODEL (materialized table, tags [marts]);\n\n"
                'SELECT order_id, amount_cents FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "staging" / "stg_orders.sql").write_text(
        direct_changes_only_stg_orders_sql(amount_cents=125, tags=", tags [staging]"),
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", test_case.selector),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    output: str = plan_result.stdout
    assert f"Plan ready ({test_case.expected_selected_count} selected)" in output, output
    for model_name in test_case.expected_model_names:
        assert model_name in output, output
    for model_name in test_case.unexpected_model_names:
        assert model_name not in output, output
    assert ("Remaining stale" in output) == bool(test_case.expected_remaining_stale_names), output
    assert ("models outside selection" in output) == bool(
        test_case.expected_remaining_stale_names
    ), output
    for model_name in test_case.expected_remaining_stale_names:
        assert model_name in output, output
