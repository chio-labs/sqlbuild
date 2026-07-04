"""E2E tests for the janitor CLI command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorActiveVirtualEnvironmentProtectionE2ETestCase,
    JanitorCheckpointProtectionE2ETestCase,
    JanitorCheckpointRetentionE2ETestCase,
    JanitorCleanupE2ETestCase,
    JanitorDetachedVirtualEnvironmentE2ETestCase,
    JanitorDetachedVirtualEnvironmentRetentionE2ETestCase,
    JanitorDirectStatePruningE2ETestCase,
    JanitorDisabledE2ETestCase,
    JanitorExpiredVirtualEnvironmentE2ETestCase,
    JanitorInvalidConfigE2ETestCase,
    JanitorStateCleanupE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.janitor.helpers import (
    create_direct_state_history,
    create_janitor_demo_relations,
    create_janitor_scenario_relations,
    prepare_janitor_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
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
    ids=lambda case: case.description,
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
                "Deleted 1 objects, deleted 0 state items, and pruned 1 direct state tables.",
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
    ids=lambda case: case.description,
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
    assert "Eligible expired VDEs" not in janitor_result.stdout
    assert "Eligible state backups" not in janitor_result.stdout
    assert "Eligible expired locks" not in janitor_result.stdout


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
                "Deleted 2 objects, deleted 0 state items, and pruned 1 direct state tables.",
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
    ids=lambda case: case.description,
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
        JanitorDirectStatePruningE2ETestCase(
            description="auto-approved janitor prunes direct state history",
            build_command=("--no-color", "build", "--full-refresh"),
            janitor_command=(
                "--no-color",
                "janitor",
                "--auto-approve",
                "--direct-state-history-versions",
                "2",
            ),
            plan_command=("--no-color", "plan"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "direct state pruned    2",
                "Eligible direct state pruning",
                "main._sqlbuild_fingerprints  keep latest 2",
                "main._sqlbuild_source_freshness  keep latest 2",
                "pruned 2 direct state tables",
            ),
            expected_fingerprint_count_before=5,
            expected_fingerprint_count_after=3,
            expected_source_freshness_count_before=4,
            expected_source_freshness_count_after=2,
            expected_fingerprint_run_ids_after=("run_003", "run_002"),
            expected_source_freshness_run_ids_after=("run_003", "run_002"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_state_history_when_running_janitor_then_it_prunes_history(
    test_case: JanitorDirectStatePruningE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_direct_state_pruning_project",
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
    create_direct_state_history(db_path=db_path)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT COUNT(*) FROM main._sqlbuild_fingerprints",
    ) == [(test_case.expected_fingerprint_count_before,)]
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT COUNT(*) FROM main._sqlbuild_source_freshness",
    ) == [(test_case.expected_source_freshness_count_before,)]

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
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT COUNT(*) FROM main._sqlbuild_fingerprints",
    ) == [(test_case.expected_fingerprint_count_after,)]
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT COUNT(*) FROM main._sqlbuild_source_freshness",
    ) == [(test_case.expected_source_freshness_count_after,)]
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT run_id FROM main._sqlbuild_fingerprints "
            "WHERE node_name = 'janitor_state_probe' ORDER BY ts DESC, run_id DESC"
        ),
    ) == [(run_id,) for run_id in test_case.expected_fingerprint_run_ids_after]
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT run_id FROM main._sqlbuild_source_freshness "
            "WHERE source_name = 'raw.janitor_state_probe' "
            "ORDER BY observed_at DESC, run_id DESC"
        ),
    ) == [(run_id,) for run_id in test_case.expected_source_freshness_run_ids_after]

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.plan_command,
        project_dir=project_dir,
    )
    assert plan_result.returncode == test_case.expected_exit_code, (
        plan_result.stdout + plan_result.stderr
    )


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
    ids=lambda case: case.description,
)
def test_given_virtual_checkpoint_refs_when_janitor_then_preserves_physical_versions(
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
            "WHERE artifact_type = 'model' AND artifact_name = 'stg_orders' "
            "ORDER BY created_at ASC LIMIT 1"
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
        JanitorExpiredVirtualEnvironmentE2ETestCase(
            description="virtual janitor prunes expired non-active VDEs",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "expired VDEs pruned",
                "Eligible expired VDEs",
                "pr  expired virtual environment",
                "Deleted 0 objects, deleted 1 state items, and pruned 0 direct state tables.",
            ),
            expected_virtual_environment_names_after=("dev",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_non_active_vde_when_running_janitor_then_it_prunes_expired_environment(
    test_case: JanitorExpiredVirtualEnvironmentE2ETestCase,
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
        project_name="virtual_janitor_expired_vde",
        repo_files=repo_files,
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name FROM sqlbuild_state.virtual_environments "
            "ORDER BY virtual_environment_name"
        ),
    ) == [(name,) for name in test_case.expected_virtual_environment_names_after]
    assert not table_exists(
        db_path=project_dir / "warehouse.duckdb",
        schema="dev__pr",
        table_name="fact_orders",
    )


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorStateCleanupE2ETestCase(
            description="virtual janitor prunes old backups and expired locks",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "state backups pruned",
                "expired locks pruned",
                "Eligible state backups",
                "Eligible expired locks",
                "Deleted 0 objects, deleted 2 state items, and pruned 0 direct state tables.",
            ),
            expected_backup_schema_count_after=1,
            expected_lock_count_after=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_state_backups_and_expired_locks_when_running_janitor_then_state_is_pruned(
    test_case: JanitorStateCleanupE2ETestCase,
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
        project_name="virtual_janitor_state_cleanup",
        repo_files=repo_files,
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("state", "migrate"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="UPDATE sqlbuild_state.state_versions SET schema_version = 2",
    )
    assert run_sqb(command=("state", "migrate"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
            "('virtual_env:stale', 'owner', TIMESTAMP '2000-01-01 00:00:00', "
            "TIMESTAMP '2000-01-01 00:00:00', TIMESTAMP '2000-01-01 00:00:00')"
        ),
    )

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.schemata "
            "WHERE schema_name LIKE 'sqlbuild_state__backup_%'"
        ),
    ) == [(test_case.expected_backup_schema_count_after,)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT COUNT(*) FROM sqlbuild_state.locks",
    ) == [(test_case.expected_lock_count_after,)]


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorStateCleanupE2ETestCase(
            description="virtual janitor keeps state cleanup refs when warehouse cleanup fails",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=1,
            expected_stdout_fragments=("simulated janitor drop failure",),
            expected_backup_schema_count_after=0,
            expected_lock_count_after=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_cleanup_failure_when_running_janitor_then_state_cleanup_is_skipped(
    test_case: JanitorStateCleanupE2ETestCase,
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
    repo_files["adapters/failing_janitor_duckdb.py"] = (
        "from typing import Any\n"
        "from sqlbuild.adapter.shared.exceptions import AdapterUserError\n"
        "from sqlbuild.adapter.shared.models import StatementRecorder\n"
        "from sqlbuild.adapters.duckdb.client import DuckDbAdapter\n\n"
        "class FailingJanitorDuckDbAdapter(DuckDbAdapter):\n"
        "    adapter_name = 'failing_janitor_duckdb'\n\n"
        "    def drop(\n"
        "        self,\n"
        "        connection: Any,\n"
        "        *,\n"
        "        destination: str,\n"
        "        if_exists: bool = True,\n"
        "        statement_recorder: StatementRecorder,\n"
        "    ) -> None:\n"
        "        raise AdapterUserError('simulated janitor drop failure')\n"
        "\n"
        "    def drop_view(\n"
        "        self,\n"
        "        connection: Any,\n"
        "        *,\n"
        "        destination: str,\n"
        "        if_exists: bool = True,\n"
        "        statement_recorder: StatementRecorder,\n"
        "    ) -> None:\n"
        "        raise AdapterUserError('simulated janitor drop failure')\n"
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_janitor_warehouse_cleanup_failure",
        repo_files=repo_files,
    )
    state_db_path: Path = project_dir / "state.duckdb"
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=state_db_path,
        sql=(
            "INSERT INTO sqlbuild_state.virtual_environments "
            "(virtual_environment_name, status, baseline_virtual_environment_name, "
            "created_at, updated_at, finalized_at) VALUES "
            "('stale', 'finalized', NULL, TIMESTAMP '2000-01-01 00:00:00', "
            "TIMESTAMP '2000-01-01 00:00:00', TIMESTAMP '2000-01-01 00:00:00')"
        ),
    )
    execute_duckdb(
        db_path=state_db_path,
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
            "('virtual_env:stale', 'owner', TIMESTAMP '2000-01-01 00:00:00', "
            "TIMESTAMP '2000-01-01 00:00:00', TIMESTAMP '2000-01-01 00:00:00')"
        ),
    )
    (project_dir / "sqlbuild_local.toml").write_text(
        'adapter = "failing_janitor_duckdb"\n', encoding="utf-8"
    )

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code
    combined_output: str = janitor_result.stdout + janitor_result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in combined_output
    assert query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.virtual_environments "
            "WHERE virtual_environment_name = 'stale'"
        ),
    ) == [(1,)]
    assert query_duckdb(
        db_path=state_db_path,
        sql="SELECT COUNT(*) FROM sqlbuild_state.locks WHERE lock_key = 'virtual_env:stale'",
    ) == [(test_case.expected_lock_count_after,)]


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorCheckpointRetentionE2ETestCase(
            description="virtual janitor prunes old checkpoints and newly unprotected physicals",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_checkpoint_count_before=3,
            expected_checkpoint_count_after=1,
            expected_stdout_fragments=(
                "checkpoints pruned",
                "Eligible checkpoints",
                "Deleted ",
                "2 checkpoints.",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_checkpoints_over_limit_when_running_janitor_then_it_prunes_old_history(
    test_case: JanitorCheckpointRetentionE2ETestCase,
    tmp_path: Path,
) -> None:
    repo_files: dict[str, str] = build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
    repo_files["sqlbuild_project.toml"] += dedent(
        """

        [janitor]
        enabled = true
        retention_days = 0
        max_checkpoints = 1
        delete_tracked_only = false
        """
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_janitor_checkpoint_retention",
        repo_files=repo_files,
    )
    state_db_path: Path = project_dir / "state.duckdb"
    warehouse_db_path: Path = project_dir / "warehouse.duckdb"

    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    first_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT physical_relations.relation_name "
            "FROM sqlbuild_state.virtual_environment_node_refs AS refs "
            "JOIN sqlbuild_state.physical_relations AS physical_relations "
            "ON physical_relations.artifact_type = 'model' "
            "AND physical_relations.artifact_name = refs.node_name "
            "AND physical_relations.version_hash = refs.version_hash "
            "WHERE refs.virtual_environment_name = 'dev' "
            "AND refs.node_type = 'model' AND refs.node_name = 'stg_orders'"
        ),
    )
    first_relation_name: str = str(first_relation_rows[0][0])

    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    latest_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT physical_relations.relation_name "
            "FROM sqlbuild_state.virtual_environment_node_refs AS refs "
            "JOIN sqlbuild_state.physical_relations AS physical_relations "
            "ON physical_relations.artifact_type = 'model' "
            "AND physical_relations.artifact_name = refs.node_name "
            "AND physical_relations.version_hash = refs.version_hash "
            "WHERE refs.virtual_environment_name = 'dev' "
            "AND refs.node_type = 'model' AND refs.node_name = 'stg_orders'"
        ),
    )
    latest_relation_name: str = str(latest_relation_rows[0][0])
    checkpoint_rows_before: list[tuple[object, ...]] = query_duckdb(
        db_path=state_db_path,
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_checkpoints",
    )

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert int(checkpoint_rows_before[0][0]) == test_case.expected_checkpoint_count_before
    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    checkpoint_rows_after: list[tuple[object, ...]] = query_duckdb(
        db_path=state_db_path,
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert int(checkpoint_rows_after[0][0]) == test_case.expected_checkpoint_count_after
    assert not table_exists(
        db_path=warehouse_db_path,
        schema="dev__sqb_physical",
        table_name=first_relation_name,
    )
    assert table_exists(
        db_path=warehouse_db_path,
        schema="dev__sqb_physical",
        table_name=latest_relation_name,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorDetachedVirtualEnvironmentE2ETestCase(
            description="virtual janitor prunes detached VDE refs and physicals",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion  1",
                "detached VDEs pruned",
                "Eligible detached VDEs",
                "dev  detached virtual environment",
                "Deleted 1 objects, deleted 1 state items, and pruned 0 direct state tables.",
            ),
            expected_virtual_environment_count_after=0,
            expected_ref_count_after=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_detached_vde_when_running_janitor_then_it_cleans_refs_and_physical_versions(
    test_case: JanitorDetachedVirtualEnvironmentE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_janitor_detached_vde",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_janitor_detached_vde"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n\n'
                "[janitor]\n"
                "enabled = true\n"
                "retention_days = 0\n"
                "delete_tracked_only = false\n"
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    warehouse_db_path: Path = project_dir / "warehouse.duckdb"
    execute_duckdb(
        db_path=warehouse_db_path,
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    adopt_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt", "--allow-copy"),
        project_dir=project_dir,
        input_text="adopt dev\n",
    )
    assert adopt_result.returncode == 0, adopt_result.stdout + adopt_result.stderr
    physical_relation_name: str = str(
        query_duckdb(
            db_path=state_db_path,
            sql=(
                "SELECT relation_name FROM sqlbuild_state.physical_relations "
                "WHERE artifact_type = 'model' AND artifact_name = 'orders'"
            ),
        )[0][0]
    )
    detach_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "detach", "--allow-copy"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )
    assert detach_result.returncode == 0, detach_result.stdout + detach_result.stderr

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    assert query_duckdb(
        db_path=state_db_path,
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environments",
    ) == [(test_case.expected_virtual_environment_count_after,)]
    assert query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type = 'model'"
        ),
    ) == [(test_case.expected_ref_count_after,)]
    assert not table_exists(
        db_path=warehouse_db_path,
        schema="dev__sqb_physical",
        table_name=physical_relation_name,
    )
    assert table_exists(db_path=warehouse_db_path, schema="dev", table_name="orders")


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorDetachedVirtualEnvironmentRetentionE2ETestCase(
            description="virtual janitor prunes only detached VDEs older than retention",
            retention_days=7,
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "7 days",
                "detached VDEs pruned",
                "Eligible detached VDEs",
                "dev  detached virtual environment",
                "Deleted 0 objects, deleted 1 state items, and pruned 0 direct state tables.",
            ),
            expected_virtual_environment_count_after=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_old_detached_vde_when_running_janitor_then_retention_allows_cleanup(
    test_case: JanitorDetachedVirtualEnvironmentRetentionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_janitor_detached_vde_retention",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_janitor_detached_vde_retention"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n\n'
                "[janitor]\n"
                "enabled = true\n"
                f"retention_days = {test_case.retention_days}\n"
                "delete_tracked_only = false\n"
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    warehouse_db_path: Path = project_dir / "warehouse.duckdb"
    execute_duckdb(
        db_path=warehouse_db_path,
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    adopt_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt", "--allow-copy"),
        project_dir=project_dir,
        input_text="adopt dev\n",
    )
    assert adopt_result.returncode == 0, adopt_result.stdout + adopt_result.stderr
    detach_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "detach", "--allow-copy"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )
    assert detach_result.returncode == 0, detach_result.stdout + detach_result.stderr
    execute_duckdb(
        db_path=state_db_path,
        sql=(
            "UPDATE sqlbuild_state.virtual_environments "
            "SET updated_at = TIMESTAMP '2026-01-01 00:00:00' "
            "WHERE virtual_environment_name = 'dev'"
        ),
    )

    janitor_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command,
        project_dir=project_dir,
    )

    assert janitor_result.returncode == test_case.expected_exit_code, (
        janitor_result.stdout + janitor_result.stderr
    )
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in janitor_result.stdout
    assert query_duckdb(
        db_path=state_db_path,
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environments",
    ) == [(test_case.expected_virtual_environment_count_after,)]


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorActiveVirtualEnvironmentProtectionE2ETestCase(
            description="virtual janitor preserves active working VDE refs",
            janitor_command=("janitor", "--auto-approve"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion  0",
                "relation is referenced by an active or retained virtual environment",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_vde_ref_when_running_janitor_then_it_preserves_physical_version(
    test_case: JanitorActiveVirtualEnvironmentProtectionE2ETestCase,
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
        project_name="virtual_janitor_active_vde_protection",
        repo_files=repo_files,
    )
    state_db_path: Path = project_dir / "state.duckdb"
    warehouse_db_path: Path = project_dir / "warehouse.duckdb"

    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    protected_relation_name: str = str(
        query_duckdb(
            db_path=state_db_path,
            sql=(
                "SELECT relation_name FROM sqlbuild_state.physical_relations "
                "WHERE artifact_type = 'model' AND artifact_name = 'stg_orders'"
            ),
        )[0][0]
    )

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
    ids=lambda case: case.description,
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
