"""E2E tests for the janitor CLI command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorCheckpointProtectionE2ETestCase,
    JanitorCleanupE2ETestCase,
    JanitorDisabledE2ETestCase,
    JanitorInvalidConfigE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.janitor.helpers import (
    create_janitor_demo_relations,
    create_janitor_scenario_relations,
    prepare_janitor_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import build_virtual_plan_repo_files
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorDisabledE2ETestCase(
            description="disabled janitor exits successfully with guidance",
            command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Janitor is disabled for this project.",
                "enabled: true",
            ),
        )
    ],
    ids=["disabled janitor exits successfully with guidance"],
)
def test_given_default_config_when_running_janitor_then_it_reports_disabled(
    test_case: JanitorDisabledE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_disabled_project",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorCleanupE2ETestCase(
            description="tracked-only janitor deletes only tracked stale relations",
            build_command=("--no-color", "build", "--full-refresh"),
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion  1",
                "objects skipped        3",
                "main.janitor_tracked_extra",
                "main.janitor_untracked_extra  relation is not tracked by SQLBuild",
                "main.partition_state  relation matches exclude pattern 'partition_*'",
                "main._sqlbuild_fingerprints  relation matches exclude pattern",
                "Deleted 1 objects.",
            ),
            expected_existing_tables=(
                "orders",
                "janitor_untracked_extra",
                "partition_state",
                "_sqlbuild_fingerprints",
            ),
            expected_missing_tables=("janitor_tracked_extra",),
        )
    ],
    ids=["tracked-only janitor deletes only tracked stale relations"],
)
def test_given_stale_relations_when_running_janitor_then_it_deletes_only_tracked(
    test_case: JanitorCleanupE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_cleanup_project",
        janitor_config=dedent(
            """
              enabled = true
              retention_days = 0
              exclude_patterns = ["partition_*"]
            """
        ),
    )
    db_path: Path = project_dir / "janitor.duckdb"

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )
    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    create_janitor_demo_relations(db_path=db_path)

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    table_name: str
    for table_name in test_case.expected_existing_tables:
        assert table_exists(db_path=db_path, table_name=table_name)
    for table_name in test_case.expected_missing_tables:
        assert not table_exists(db_path=db_path, table_name=table_name)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorCleanupE2ETestCase(
            description="tracked-only janitor deletes strict scenario artifacts",
            build_command=("--no-color", "build", "--full-refresh"),
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion  2",
                "objects skipped        2",
                "main.__sqb_a13f09c2e7b8__model__daily_revenue",
                "main.__sqb_a13f09c2e7b8__source__raw_orders",
                "main.__sqb_a13f09c2e7b__model__daily_revenue  relation is not tracked by SQLBuild",
                "Deleted 2 objects.",
            ),
            expected_existing_tables=(
                "orders",
                "__sqb_a13f09c2e7b__model__daily_revenue",
            ),
            expected_missing_tables=(
                "__sqb_a13f09c2e7b8__source__raw_orders",
                "__sqb_a13f09c2e7b8__model__daily_revenue",
            ),
        )
    ],
    ids=["tracked-only janitor deletes strict scenario artifacts"],
)
def test_given_scenario_artifacts_when_running_tracked_only_janitor_then_it_deletes_them(
    test_case: JanitorCleanupE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_scenario_cleanup_project",
        janitor_config=dedent(
            """
              enabled = true
              retention_days = 0
            """
        ),
    )
    db_path: Path = project_dir / "janitor.duckdb"

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )
    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    create_janitor_scenario_relations(db_path=db_path)

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    table_name: str
    for table_name in test_case.expected_existing_tables:
        assert table_exists(db_path=db_path, table_name=table_name)
    for table_name in test_case.expected_missing_tables:
        assert not table_exists(db_path=db_path, table_name=table_name)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorCheckpointProtectionE2ETestCase(
            description="virtual janitor preserves checkpoint referenced physical versions",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion  0",
                "relation is referenced by a retained virtual checkpoint",
            ),
        )
    ],
    ids=["virtual janitor preserves checkpoint referenced physical versions"],
)
def test_given_virtual_checkpoint_refs_when_running_janitor_then_it_preserves_physical_versions(
    test_case: JanitorCheckpointProtectionE2ETestCase,
    tmp_path: Path,
) -> None:
    repo_files: dict[str, str] = build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
    repo_files["sqlbuild_project.toml"] += dedent(
        """

        [janitor]
        enabled = true
        retention_days = 0
        delete_tracked_only = false
        """
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_janitor_checkpoint_protection",
        repo_files=repo_files,
    )
    state_db_path: Path = project_dir / "state.duckdb"
    warehouse_db_path: Path = project_dir / "warehouse.duckdb"

    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    protected_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT relation_name FROM sqlbuild_state.physical_relations "
            "WHERE model_name = 'stg_orders' ORDER BY created_at ASC LIMIT 1"
        ),
    )
    protected_relation_name: str = str(protected_relation_rows[0][0])
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    assert table_exists(
        db_path=warehouse_db_path,
        schema="dev__sqb_physical",
        table_name=protected_relation_name,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorInvalidConfigE2ETestCase(
            description="tracked-only janitor requires query tracking",
            command=("janitor", "--auto-approve"),
            expected_exit_code=1,
            expected_stderr_fragments=("janitor.delete_tracked_only requires",),
        )
    ],
    ids=["tracked-only janitor requires query tracking"],
)
def test_given_query_tracking_disabled_when_running_tracked_only_janitor_then_it_errors(
    test_case: JanitorInvalidConfigE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_invalid_config_project",
        settings_config="query_change_tracking = false\n",
        janitor_config="enabled = true\n",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
