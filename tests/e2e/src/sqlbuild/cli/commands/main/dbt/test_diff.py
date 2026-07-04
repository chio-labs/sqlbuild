from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtDiffConfigErrorE2ETestCase,
    DbtDiffE2ETestCase,
    DbtDiffErrorE2ETestCase,
    DbtDiffSelectionE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    build_dbt_diff_current_model,
    prepare_dbt_diff_workspace,
    skip_unless_dbt_is_runnable,
    write_dbt_diff_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDiffE2ETestCase(
            description="schema-only diff reports no schema differences",
            command=("--no-color", "dbt", "diff", "--select", "dbt_orders", "--schema-only"),
            expected_returncode=0,
            expected_stdout_fragments=(
                "SQLBuild Diff Summary",
                "prod vs current",
                "No schema differences.",
            ),
            expected_absent_stdout_fragments=("Rows",),
            expected_stderr_fragments=(
                "Compiling dbt project...",
                "Compiling dbt production ref git ref 'prod'...",
                "Resolving dbt selection...",
                "Connecting to duckdb...",
                "Comparing dbt relations...",
                "Compared dbt relations.",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unchanged_model_when_diffing_schema_only_then_reports_no_differences(
    tmp_path: Path,
    test_case: DbtDiffE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path, workspace_name="diff_schema_only_workspace"
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    for fragment in test_case.expected_absent_stdout_fragments:
        assert fragment not in result.stdout
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDiffE2ETestCase(
            description="full diff reports row differences against production",
            command=("--no-color", "dbt", "diff", "--select", "dbt_orders", "--full"),
            expected_returncode=1,
            expected_stdout_fragments=(
                "prod vs current",
                "Rows",
                "amount_cents",
                "900 -> 111",
                "prod only",
                "order_id=2",
                "current only",
                "order_id=3",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_changed_model_when_diffing_full_then_reports_row_differences(
    tmp_path: Path,
    test_case: DbtDiffE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path, workspace_name="diff_full_workspace"
    )
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=111,
        order_ids=(1, 3),
        include_unique_key=True,
        include_cursor_meta=True,
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDiffE2ETestCase(
            description="bounded diff uses model cursor metadata",
            command=("--no-color", "dbt", "diff", "--select", "dbt_orders", "--bounded", "3650d"),
            expected_returncode=1,
            expected_stdout_fragments=(
                "prod vs current",
                "bounded 3650d",
                "Rows",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_metadata_when_diffing_bounded_then_reports_rows(
    tmp_path: Path,
    test_case: DbtDiffE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path, workspace_name="diff_bounded_workspace"
    )
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=111,
        order_ids=(1, 3),
        include_unique_key=True,
        include_cursor_meta=True,
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    (
        DbtDiffErrorE2ETestCase(
            description="full diff without unique key explains how to fix",
            command=("dbt", "diff", "--select", "dbt_orders", "--full"),
            include_unique_key=False,
            include_cursor_meta=True,
            expected_returncode=1,
            expected_stderr_fragments=(
                "requires model 'dbt_orders' to define config.unique_key",
                "--schema-only",
            ),
        ),
        DbtDiffErrorE2ETestCase(
            description="bounded diff without cursor metadata explains how to fix",
            command=("dbt", "diff", "--select", "dbt_orders", "--bounded", "7d"),
            include_unique_key=True,
            include_cursor_meta=False,
            expected_returncode=1,
            expected_stderr_fragments=(
                "requires model 'dbt_orders' to define SQLBuild cursor metadata",
                "meta.sqlbuild.cursor",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_missing_diff_metadata_when_diffing_then_error_explains_fix(
    tmp_path: Path,
    test_case: DbtDiffErrorE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="diff_error_workspace",
        include_unique_key=test_case.include_unique_key,
        include_cursor_meta=test_case.include_cursor_meta,
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    (
        DbtDiffConfigErrorE2ETestCase(
            description="missing production_ref config explains how to configure",
            command=("dbt", "diff", "--select", "dbt_orders", "--schema-only"),
            include_production_ref=False,
            production_ref_git_ref="prod",
            expected_returncode=1,
            expected_stderr_fragments=(
                "dbt diff requires [dbt.production_ref] to be configured",
                "sqb dbt init",
            ),
        ),
        DbtDiffConfigErrorE2ETestCase(
            description="invalid reuse git ref explains how to fix",
            command=("dbt", "diff", "--select", "dbt_orders", "--schema-only"),
            include_production_ref=True,
            production_ref_git_ref="does-not-exist",
            expected_returncode=1,
            expected_stderr_fragments=(
                "dbt production_ref git_ref 'does-not-exist' does not exist in this repository",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_diff_config_when_diffing_then_error_explains_fix(
    tmp_path: Path,
    test_case: DbtDiffConfigErrorE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="diff_config_error_workspace",
        include_production_ref=test_case.include_production_ref,
        production_ref_git_ref=test_case.production_ref_git_ref,
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    (
        DbtDiffSelectionE2ETestCase(
            description="multi select shows both models and exclude narrows them",
            command=(
                "--no-color",
                "dbt",
                "diff",
                "--select",
                "dbt_orders",
                "dbt_customers",
                "--exclude",
                "dbt_customers",
                "--schema-only",
            ),
            expected_returncode=0,
            expected_stdout_fragments=("dbt_orders",),
            expected_absent_stdout_fragments=("dbt_customers",),
        ),
        DbtDiffSelectionE2ETestCase(
            description="multi select shows both models",
            command=(
                "--no-color",
                "dbt",
                "diff",
                "--select",
                "dbt_orders",
                "dbt_customers",
                "--schema-only",
            ),
            expected_returncode=0,
            expected_stdout_fragments=("dbt_orders", "dbt_customers", "selected models: 2"),
        ),
        DbtDiffSelectionE2ETestCase(
            description="tag selector flows through to dbt diff",
            command=(
                "--no-color",
                "dbt",
                "diff",
                "--select",
                "tag:finance",
                "--schema-only",
            ),
            expected_returncode=0,
            expected_stdout_fragments=("dbt_customers", "selected models: 1"),
            expected_absent_stdout_fragments=("dbt_orders",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_diff_selectors_when_diffing_then_scopes_models(
    tmp_path: Path,
    test_case: DbtDiffSelectionE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="diff_selection_workspace",
        include_second_model=True,
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    for fragment in test_case.expected_absent_stdout_fragments:
        assert fragment not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDiffE2ETestCase(
            description="schema diff detects added column",
            command=("--no-color", "dbt", "diff", "--select", "dbt_orders", "--schema-only"),
            expected_returncode=1,
            expected_stdout_fragments=("Schemas", "schema differences: 1", "added columns: 1"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_added_column_when_diffing_schema_only_then_reports_schema_difference(
    tmp_path: Path,
    test_case: DbtDiffE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path, workspace_name="diff_schema_change_workspace"
    )
    workspace.joinpath("dbt_project", "models", "dbt_orders.sql").write_text(
        "{{ config(\n"
        "    materialized='table',\n"
        "    unique_key='order_id',\n"
        "    meta={'sqlbuild': {'cursor': 'updated_at', 'cursor_type': 'timestamp'}}\n"
        ") }}\n\n"
        "select 1 as order_id, 900 as amount_cents, "
        "cast('2026-06-17 00:00:00' as timestamp) as updated_at, 'usd' as currency\n",
        encoding="utf-8",
    )
    build_dbt_diff_current_model(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
