"""CLI e2e coverage for renaming incremental model columns in place across builds."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    ColumnMigrationLifecycleE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    build,
    column_migration_events,
    fct_order_columns,
    fct_order_values,
    fct_orders_sql,
    load_raw_order_amounts,
    plan_output,
    plan_payload,
    write_fct_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnMigrationLifecycleE2ETestCase(
            description="automatic, retried, declared, and near-match renames",
            expected_automatic_plan=(
                "Column migrations (1)\n└── fct_orders  migrate columns\n"
                "    └── amount -> revenue  rename in place  (automatic)\n"
            ),
            expected_retry_decisions=("done",),
            expected_revenue=((1, 101), (2, 102), (3, 103), (4, 104), (5, 105)),
            expected_declared_notice=(
                "migrate_from can be removed from column 'net_revenue' of 'fct_orders'"
            ),
            expected_near_match_hint=(
                "similar to net_revenue; if this is a rename, add gross (migrate_from net_revenue)"
            ),
            expected_final_columns=("order_id", "order_date", "net_revenue", "gross"),
            expected_events=(
                ("amount", "revenue", "automatic", "rename"),
                ("revenue", "net_revenue", "manual", "rename"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_columns_when_building_through_the_cli_then_history_follows_each_rename(
    tmp_path: Path, test_case: ColumnMigrationLifecycleE2ETestCase
) -> None:
    """The real CLI renames in place, survives a failed delta, and hints near matches."""

    project_dir: Path = write_fct_orders_project(
        tmp_path=tmp_path, model_sql=fct_orders_sql(columns="amount")
    )
    load_raw_order_amounts(project_dir=project_dir, last_day=3)
    initial: subprocess.CompletedProcess[str] = build(project_dir=project_dir)

    _ = write_fct_orders_project(
        tmp_path=tmp_path, model_sql=fct_orders_sql(columns="amount AS revenue")
    )
    load_raw_order_amounts(project_dir=project_dir, last_day=5, changed_day=1, failing_day=5)
    automatic_plan: str = plan_output(project_dir=project_dir)
    failed: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    columns_after_failure: tuple[str, ...] = fct_order_columns(project_dir=project_dir)

    load_raw_order_amounts(project_dir=project_dir, last_day=5, changed_day=1)
    retry_plan: dict[str, Any] = plan_payload(project_dir=project_dir)
    retried: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    revenue: tuple[tuple[int, int], ...] = fct_order_values(
        project_dir=project_dir, column="revenue"
    )

    _ = write_fct_orders_project(
        tmp_path=tmp_path,
        model_sql=fct_orders_sql(
            columns="amount AS net_revenue",
            extra_config="  columns (net_revenue (migrate_from revenue)),\n",
        ),
    )
    declared: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    recorded: subprocess.CompletedProcess[str] = build(project_dir=project_dir)

    _ = write_fct_orders_project(
        tmp_path=tmp_path,
        model_sql=fct_orders_sql(
            columns="amount AS net_revenue, ROUND(amount * 1.5) AS gross", replay=False
        ),
    )
    near_match_plan: str = plan_output(project_dir=project_dir)
    _ = write_fct_orders_project(
        tmp_path=tmp_path,
        model_sql=fct_orders_sql(columns="ROUND(amount * 1.5) AS gross", replay=False),
    )
    near_match_hint_plan: str = plan_output(project_dir=project_dir)
    near_match: subprocess.CompletedProcess[str] = build(project_dir=project_dir)
    after_near_match_plan: str = plan_output(project_dir=project_dir)

    assert initial.returncode == 0, initial.stdout + initial.stderr
    assert test_case.expected_automatic_plan in automatic_plan
    assert failed.returncode != 0
    assert columns_after_failure == ("order_id", "order_date", "revenue")
    assert tuple(entry["decision"] for entry in retry_plan["column_migrations"]) == (
        test_case.expected_retry_decisions
    )
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert "Renaming columns" not in retried.stdout + retried.stderr
    assert revenue == test_case.expected_revenue
    assert declared.returncode == 0, declared.stdout + declared.stderr
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    assert recorded.stdout.count(test_case.expected_declared_notice) == 1
    assert "Completed successfully" in recorded.stdout.rstrip().splitlines()[-1]
    assert "Column migrations" not in near_match_plan
    assert test_case.expected_near_match_hint in near_match_hint_plan
    assert near_match.returncode == 0, near_match.stdout + near_match.stderr
    assert test_case.expected_near_match_hint not in after_near_match_plan
    assert fct_order_columns(project_dir=project_dir) == test_case.expected_final_columns
    assert column_migration_events(project_dir=project_dir) == test_case.expected_events


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
