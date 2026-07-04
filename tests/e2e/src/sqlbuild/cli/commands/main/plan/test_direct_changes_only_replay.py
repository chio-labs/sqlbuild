"""Direct changes-only replay policy E2E tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectChangesOnlyFunctionReplayE2ETestCase,
    DirectChangesOnlyReplayE2ETestCase,
    DirectChangesOnlySchemaReplayE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_direct_changes_only_project_toml,
    direct_changes_only_orders_model_sql,
    only_json_model,
    plan_changes_only_json,
    prepare_direct_changes_only_incremental_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyReplayE2ETestCase(
            description="default forward replay policy",
            policy_fragment="",
            expected_backfill_action="forward",
            expected_backfill_duration=None,
        ),
        DirectChangesOnlyReplayE2ETestCase(
            description="full replay policy",
            policy_fragment=", replay_on_change full",
            expected_backfill_action="full",
            expected_backfill_duration=None,
        ),
        DirectChangesOnlyReplayE2ETestCase(
            description="bounded replay policy",
            policy_fragment=", replay_on_change bounded-14d",
            expected_backfill_action="bounded",
            expected_backfill_duration="14d",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_direct_query_change_when_planning_changes_only_json_then_reports_replay_policy(
    test_case: DirectChangesOnlyReplayE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_changes_only_incremental_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_query_replay",
        model_sql=direct_changes_only_orders_model_sql(
            amount_expression="100",
            policy_fragment=test_case.policy_fragment,
            columns_fragment="",
        ),
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "orders.sql").write_text(
        direct_changes_only_orders_model_sql(
            amount_expression="100 + 0",
            policy_fragment=test_case.policy_fragment,
            columns_fragment="",
        ),
        encoding="utf-8",
    )

    payload: dict[str, object] = plan_changes_only_json(project_dir=project_dir)

    model: dict[str, object] = only_json_model(payload)
    assert model["name"] == "orders"
    assert model["reason"] == "query_changed"
    assert model["backfill"] == {
        "action": test_case.expected_backfill_action,
        "duration": test_case.expected_backfill_duration,
    }


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlySchemaReplayE2ETestCase(
            description="schema change uses full replay policy",
            expected_reason="schema_changed",
            expected_backfill_action="full",
            expected_backfill_duration=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_schema_change_when_planning_changes_only_json_then_uses_replay_on_change(
    test_case: DirectChangesOnlySchemaReplayE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_changes_only_incremental_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_schema_replay",
        model_sql=direct_changes_only_orders_model_sql(
            amount_expression="100",
            policy_fragment=", on_schema_change append_new_columns, replay_on_change full",
            columns_fragment="columns (id (type INTEGER), amount_cents (type INTEGER)),",
        ),
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "orders.sql").write_text(
        direct_changes_only_orders_model_sql(
            amount_expression="100",
            policy_fragment=", on_schema_change append_new_columns, replay_on_change full",
            columns_fragment=(
                "columns (id (type INTEGER), amount_cents (type INTEGER), "
                "amount_dollars (type DOUBLE)),"
            ),
        ),
        encoding="utf-8",
    )

    payload: dict[str, object] = plan_changes_only_json(project_dir=project_dir)

    model: dict[str, object] = only_json_model(payload)
    assert model["name"] == "orders"
    assert model["reason"] == test_case.expected_reason
    assert model["backfill"] == {
        "action": test_case.expected_backfill_action,
        "duration": test_case.expected_backfill_duration,
    }


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyFunctionReplayE2ETestCase(
            description="function change uses bounded replay policy",
            expected_reason="upstream_changed",
            expected_backfill_action="bounded",
            expected_backfill_duration="14d",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_change_when_planning_json_then_uses_function_replay_on_change(
    test_case: DirectChangesOnlyFunctionReplayE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_function_replay",
        repo_files={
            "sqlbuild_project.toml": build_direct_changes_only_project_toml(
                project_name="direct_changes_only_function_replay"
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change bounded-14d);\n\namount > 100\n"
            ),
            "models/orders.sql": (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  cursor id,\n"
                "  cursor_type integer,\n"
                "  unique_key id\n"
                ");\n\n"
                'SELECT 1 AS id, __udf("is_large_order")(150) AS is_large\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
        "replay_on_change bounded-14d);\n\namount >= 100\n",
        encoding="utf-8",
    )

    payload: dict[str, object] = plan_changes_only_json(project_dir=project_dir)

    model: dict[str, object] = only_json_model(payload)
    assert model["name"] == "orders"
    assert model["reason"] == test_case.expected_reason
    assert model["backfill"] == {
        "action": test_case.expected_backfill_action,
        "duration": test_case.expected_backfill_duration,
    }
