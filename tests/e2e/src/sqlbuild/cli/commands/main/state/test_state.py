from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)
from tests.e2e.src.sqlbuild.cli.commands.main.state._test_types import (
    StateExplicitRollbackE2ETestCase,
    StateLifecycleE2ETestCase,
    StateLifecycleErrorE2ETestCase,
    StateLocalOverrideE2ETestCase,
    StateModeGuardE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.state.helpers import assert_state_cli_error

STATE_LIFECYCLE_ERROR_E2E_TEST_CASES: tuple[StateLifecycleErrorE2ETestCase, ...] = (
    StateLifecycleErrorE2ETestCase(
        description="reset blocks when allow reset is false",
        project_toml="""
name = "versioned_state_project"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
allow_reset = false

[environments.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        command=("--no-color", "state", "reset", "--auto-approve"),
        expected_exit_code=1,
        expected_error_fragment=("set `allow_reset = true` under `[environments.<name>.state]`"),
    ),
    StateLifecycleErrorE2ETestCase(
        description="reset blocks without auto approve",
        project_toml="""
name = "versioned_state_project"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
allow_reset = true

[environments.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        command=("--no-color", "state", "reset"),
        expected_exit_code=1,
        expected_error_fragment="state reset requires --auto-approve",
    ),
    StateLifecycleErrorE2ETestCase(
        description="rollback blocks before backup exists",
        project_toml="""
name = "versioned_state_project"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[environments.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        command=("--no-color", "state", "rollback"),
        expected_exit_code=1,
        expected_error_fragment="No state backup is available for rollback",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateLifecycleE2ETestCase(
            description="duckdb state lifecycle commands manage state tables",
            expected_exit_code=0,
            expected_init_fragment="Virtual State Initialized",
            expected_migrate_fragment="Virtual State Migrated",
            expected_rollback_fragment="Virtual State Rolled Back",
            expected_reset_fragment="Virtual State Reset",
            expected_schema_version=1,
            expected_init_fragments=(
                "function_versions",
                "virtual_environment_function_refs",
                "virtual_environment_checkpoint_function_refs",
            ),
        )
    ],
    ids=["duckdb state lifecycle commands manage state tables"],
)
def test_given_duckdb_state_config_when_running_state_lifecycle_then_state_store_is_updated(
    test_case: StateLifecycleE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="versioned_state_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "versioned_state_project"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
allow_reset = true

[environments.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == test_case.expected_exit_code, (
        init_result.stdout + init_result.stderr
    )
    assert test_case.expected_init_fragment in init_result.stdout
    for fragment in test_case.expected_init_fragments:
        assert fragment in init_result.stdout
    assert query_duckdb(
        db_path=state_db_path,
        sql="SELECT schema_version FROM sqlbuild_state.state_versions",
    ) == [(test_case.expected_schema_version,)]

    migrate_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "migrate"),
        project_dir=project_dir,
    )
    assert migrate_result.returncode == test_case.expected_exit_code, (
        migrate_result.stdout + migrate_result.stderr
    )
    assert test_case.expected_migrate_fragment in migrate_result.stdout

    execute_duckdb(
        db_path=state_db_path,
        sql="DELETE FROM sqlbuild_state.state_versions",
    )
    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "rollback"),
        project_dir=project_dir,
    )
    assert rollback_result.returncode == test_case.expected_exit_code, (
        rollback_result.stdout + rollback_result.stderr
    )
    assert test_case.expected_rollback_fragment in rollback_result.stdout
    assert query_duckdb(
        db_path=state_db_path,
        sql="SELECT schema_version FROM sqlbuild_state.state_versions",
    ) == [(test_case.expected_schema_version,)]

    reset_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "reset", "--auto-approve"),
        project_dir=project_dir,
    )
    assert reset_result.returncode == test_case.expected_exit_code, (
        reset_result.stdout + reset_result.stderr
    )
    assert test_case.expected_reset_fragment in reset_result.stdout
    assert query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'sqlbuild_state' AND table_name = 'state_versions'"
        ),
    ) == [(0,)]


@pytest.mark.parametrize(
    "test_case",
    STATE_LIFECYCLE_ERROR_E2E_TEST_CASES,
    ids=[case.description for case in STATE_LIFECYCLE_ERROR_E2E_TEST_CASES],
)
def test_given_duckdb_state_config_when_running_blocked_state_command_then_cli_reports_error(
    test_case: StateLifecycleErrorE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="versioned_state_project",
        repo_files={"sqlbuild_project.toml": test_case.project_toml},
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert_state_cli_error(
        result=result,
        expected_exit_code=test_case.expected_exit_code,
        expected_error_fragment=test_case.expected_error_fragment,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="state init blocks outside virtual mode",
            project_toml="""
name = "versioned_state_project"
adapter = "duckdb"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[environments.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
            expected_exit_code=1,
            expected_error_fragment="State commands require environment_mode = 'virtual'",
        )
    ],
    ids=["state init blocks outside virtual mode"],
)
def test_given_direct_mode_project_when_running_state_init_then_cli_blocks_cleanly(
    test_case: StateModeGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="versioned_state_project",
        repo_files={"sqlbuild_project.toml": test_case.project_toml},
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "init"),
        project_dir=project_dir,
    )

    assert_state_cli_error(
        result=result,
        expected_exit_code=test_case.expected_exit_code,
        expected_error_fragment=test_case.expected_error_fragment,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StateLocalOverrideE2ETestCase(
            description="local state connection override controls CLI state database",
            expected_exit_code=0,
            expected_schema_version=1,
        )
    ],
    ids=["local state connection override controls CLI state database"],
)
def test_given_local_state_override_when_running_state_init_then_cli_uses_local_state_database(
    test_case: StateLocalOverrideE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="versioned_state_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "versioned_state_project"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[environments.dev.state.connection]
database = "project-state.duckdb"
""".lstrip(),
            "sqlbuild_local.toml": """
[environments.dev.state.connection]
database = "local-state.duckdb"
""".lstrip(),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "init"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert query_duckdb(
        db_path=project_dir / "local-state.duckdb",
        sql="SELECT schema_version FROM sqlbuild_state.state_versions",
    ) == [(test_case.expected_schema_version,)]
    assert not (project_dir / "project-state.duckdb").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        StateExplicitRollbackE2ETestCase(
            description="rollback accepts explicit backup id",
            expected_exit_code=0,
            expected_rollback_fragment="Virtual State Rolled Back",
            expected_schema_version=1,
        )
    ],
    ids=["rollback accepts explicit backup id"],
)
def test_given_duckdb_state_backup_when_rolling_back_explicit_backup_id_then_restores_backup(
    test_case: StateExplicitRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="versioned_state_project",
        repo_files={
            "sqlbuild_project.toml": """
name = "versioned_state_project"
adapter = "duckdb"
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "warehouse.duckdb"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[environments.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == test_case.expected_exit_code, (
        init_result.stdout + init_result.stderr
    )
    migrate_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "migrate"),
        project_dir=project_dir,
    )
    assert migrate_result.returncode == test_case.expected_exit_code, (
        migrate_result.stdout + migrate_result.stderr
    )
    backup_id: str = query_duckdb(
        db_path=state_db_path,
        sql=(
            "SELECT backup_id FROM sqlbuild_state.state_migration_events "
            "WHERE action = 'backup' ORDER BY created_at DESC LIMIT 1"
        ),
    )[0][0]
    execute_duckdb(
        db_path=state_db_path,
        sql="UPDATE sqlbuild_state.state_versions SET schema_version = 2",
    )
    second_migrate_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "migrate"),
        project_dir=project_dir,
    )
    assert second_migrate_result.returncode == test_case.expected_exit_code, (
        second_migrate_result.stdout + second_migrate_result.stderr
    )
    execute_duckdb(db_path=state_db_path, sql="DELETE FROM sqlbuild_state.state_versions")

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "rollback", "--backup-id", backup_id),
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code, (
        rollback_result.stdout + rollback_result.stderr
    )
    assert test_case.expected_rollback_fragment in rollback_result.stdout
    assert query_duckdb(
        db_path=state_db_path,
        sql="SELECT schema_version FROM sqlbuild_state.state_versions",
    ) == [(test_case.expected_schema_version,)]
