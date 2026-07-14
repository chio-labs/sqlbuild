from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.state._test_types import (
    StateAdoptDetachE2ETestCase,
    StateExplicitRollbackE2ETestCase,
    StateLifecycleE2ETestCase,
    StateLifecycleErrorE2ETestCase,
    StateLocalOverrideE2ETestCase,
    StateModeGuardE2ETestCase,
    StateSchemaCorruptionE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.state.helpers import assert_state_cli_error
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
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
                "physical_relation_ancestry",
                "function_versions",
                "virtual_environment_node_refs",
                "virtual_environment_checkpoint_function_refs",
            ),
        )
    ],
    ids=lambda case: case.description,
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
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
allow_reset = true

[targets.dev.state.connection]
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
    [
        StateModeGuardE2ETestCase(
            description="explicit rollback blocks cleanly when backup schema is deleted",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="sqlbuild_state__backup_",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deleted_duckdb_state_backup_when_rolling_back_then_it_blocks_cleanly(
    test_case: StateModeGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="duckdb_state_deleted_backup",
        repo_files={
            "sqlbuild_project.toml": """
name = "duckdb_state_deleted_backup"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip()
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("state", "migrate"), project_dir=project_dir).returncode == 0
    backup_id: str = str(
        query_duckdb(
            db_path=state_db_path,
            sql=(
                "SELECT backup_id FROM sqlbuild_state.state_migration_events "
                "WHERE action = 'backup' ORDER BY created_at DESC LIMIT 1"
            ),
        )[0][0]
    )
    execute_duckdb(
        db_path=state_db_path,
        sql=f'DROP SCHEMA "sqlbuild_state__backup_{backup_id}" CASCADE',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "rollback", "--backup-id", backup_id),
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
            description="latest rollback blocks cleanly when backup schema is deleted",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="No state backup is available for rollback",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deleted_latest_duckdb_state_backup_when_rolling_back_then_it_blocks_cleanly(
    test_case: StateModeGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="duckdb_state_deleted_latest_backup",
        repo_files={
            "sqlbuild_project.toml": """
name = "duckdb_state_deleted_latest_backup"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip()
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("state", "migrate"), project_dir=project_dir).returncode == 0
    backup_id: str = str(
        query_duckdb(
            db_path=state_db_path,
            sql=(
                "SELECT backup_id FROM sqlbuild_state.state_migration_events "
                "WHERE action = 'backup' ORDER BY created_at DESC LIMIT 1"
            ),
        )[0][0]
    )
    execute_duckdb(
        db_path=state_db_path,
        sql=f'DROP SCHEMA "sqlbuild_state__backup_{backup_id}" CASCADE',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "rollback"),
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
            description="migrate blocks cleanly when required state table is missing",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="Cannot backup invalid state schema",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_duckdb_state_table_when_migrating_then_cli_blocks_cleanly(
    test_case: StateModeGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="duckdb_state_missing_table",
        repo_files={
            "sqlbuild_project.toml": """
name = "duckdb_state_missing_table"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip()
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=state_db_path,
        sql='DROP TABLE "sqlbuild_state"."virtual_environment_node_refs"',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "migrate"),
        project_dir=project_dir,
    )

    assert_state_cli_error(
        result=result,
        expected_exit_code=test_case.expected_exit_code,
        expected_error_fragment=test_case.expected_error_fragment,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        StateSchemaCorruptionE2ETestCase(
            description="migrate blocks cleanly when required state column is missing",
            mutation_sql='ALTER TABLE "sqlbuild_state"."state_versions" DROP COLUMN "updated_at"',
            expected_exit_code=1,
            expected_error_fragment="Cannot backup invalid state schema",
        ),
        StateSchemaCorruptionE2ETestCase(
            description="migrate blocks cleanly when required state column has wrong type",
            mutation_sql=(
                'ALTER TABLE "sqlbuild_state"."state_versions" '
                'ALTER COLUMN "schema_version" SET DATA TYPE TEXT'
            ),
            expected_exit_code=1,
            expected_error_fragment="Cannot backup invalid state schema",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_corrupt_duckdb_state_schema_when_migrating_then_cli_blocks_cleanly(
    test_case: StateSchemaCorruptionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="duckdb_state_schema_corruption",
        repo_files={
            "sqlbuild_project.toml": """
name = "duckdb_state_schema_corruption"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip()
        },
    )
    state_db_path: Path = project_dir / "state.duckdb"
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    execute_duckdb(db_path=state_db_path, sql=test_case.mutation_sql)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "migrate"),
        project_dir=project_dir,
    )

    assert_state_cli_error(
        result=result,
        expected_exit_code=test_case.expected_exit_code,
        expected_error_fragment=test_case.expected_error_fragment,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        StateLifecycleErrorE2ETestCase(
            description="reset blocks when allow reset is false",
            project_toml="""
name = "versioned_state_project"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
allow_reset = false

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
            command=("--no-color", "state", "reset", "--auto-approve"),
            expected_exit_code=1,
            expected_error_fragment=("set `allow_reset = true` under `[targets.<name>.state]`"),
        ),
        StateLifecycleErrorE2ETestCase(
            description="reset blocks without auto approve",
            project_toml="""
name = "versioned_state_project"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"
allow_reset = true

[targets.dev.state.connection]
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
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
            command=("--no-color", "state", "rollback"),
            expected_exit_code=1,
            expected_error_fragment="No state backup is available for rollback",
        ),
    ),
    ids=lambda case: case.description,
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
default_target = "dev"

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
            expected_exit_code=1,
            expected_error_fragment="State commands require virtual_environments = true",
        )
    ],
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "project-state.duckdb"
""".lstrip(),
            "sqlbuild_local.toml": """
[targets.dev.state.connection]
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
        StateAdoptDetachE2ETestCase(
            description="adopt and detach preserve unsuffixed logical names interactively",
            expected_adopt_fragment="Adopted 1 models into virtual environment dev.",
            expected_detach_fragment="Detached 1 models from virtual environment dev.",
            expected_detached_status="detached",
            expected_operation_rows=(
                ("adopt:dev", "adopt", "succeeded", "dev"),
                ("detach:dev", "detach", "succeeded", "dev"),
            ),
            expected_operation_event_rows=(
                ("adopt:dev", "start", "running", "starting adopt"),
                ("adopt:dev", "finish", "succeeded", "adopted 1 models"),
                ("detach:dev", "start", "running", "starting detach"),
                ("detach:dev", "finish", "succeeded", "detached 1 models"),
            ),
            expected_detached_error_fragment="detached",
            expected_query_results_after_adopt=(("SELECT id FROM dev.orders", ((1,),)),),
            expected_query_results_after_detach=(("SELECT id FROM dev.orders", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsuffixed_virtual_environment_when_adopting_and_detaching_then_names_are_preserved(
    test_case: StateAdoptDetachE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_adopt_detach",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_adopt_detach"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0

    adopt_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt", "--allow-copy"),
        project_dir=project_dir,
        input_text="adopt dev\n",
    )
    assert adopt_result.returncode == 0, adopt_result.stdout + adopt_result.stderr
    assert test_case.expected_adopt_fragment in adopt_result.stdout + adopt_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results_after_adopt:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )

    detach_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "detach", "--allow-copy"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )
    assert detach_result.returncode == 0, detach_result.stdout + detach_result.stderr
    assert test_case.expected_detach_fragment in detach_result.stdout + detach_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results_after_detach:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT status FROM sqlbuild_state.virtual_environments "
            "WHERE virtual_environment_name = 'dev'"
        ),
    ) == [(test_case.expected_detached_status,)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model'"
        ),
    ) == [("orders",)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT operation_id, operation_type, status, virtual_environment_name "
            "FROM sqlbuild_state.state_operations ORDER BY operation_id"
        ),
    ) == list(test_case.expected_operation_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT operation_id, action, status, message "
            "FROM sqlbuild_state.state_operation_events ORDER BY operation_id, created_at"
        ),
    ) == list(test_case.expected_operation_event_rows)

    build_after_detach: subprocess.CompletedProcess[str] = run_sqb(
        command=("build",),
        project_dir=project_dir,
    )
    assert build_after_detach.returncode == 1, build_after_detach.stdout + build_after_detach.stderr
    assert test_case.expected_detached_error_fragment in (
        build_after_detach.stdout + build_after_detach.stderr
    )

    promote_after_detach: subprocess.CompletedProcess[str] = run_sqb(
        command=("promote", "--from", "dev", "--to", "prod"),
        project_dir=project_dir,
    )
    assert promote_after_detach.returncode == 1, (
        promote_after_detach.stdout + promote_after_detach.stderr
    )
    assert test_case.expected_detached_error_fragment in (
        promote_after_detach.stdout + promote_after_detach.stderr
    )

    rollback_after_detach: subprocess.CompletedProcess[str] = run_sqb(
        command=("rollback",),
        project_dir=project_dir,
    )
    assert rollback_after_detach.returncode == 1, (
        rollback_after_detach.stdout + rollback_after_detach.stderr
    )
    assert test_case.expected_detached_error_fragment in (
        rollback_after_detach.stdout + rollback_after_detach.stderr
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="adopt blocks without unsuffixed virtual env",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="unsuffixed_virtual_env",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_unsuffixed_virtual_env_when_adopting_then_it_blocks_with_config_error(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_adopt_missing_unsuffixed",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_adopt_missing_unsuffixed"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt"),
        project_dir=project_dir,
        input_text="adopt dev\n",
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="adopt blocks copy fallback without explicit permission",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="requires --allow-copy",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_copy_fallback_required_when_adopting_without_allow_copy_then_it_blocks(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_adopt_allow_copy_required",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_adopt_allow_copy_required"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt"),
        project_dir=project_dir,
        input_text="adopt dev\n",
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="interrupted detach records failed operation",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="simulated detach copy failure",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_detach_copy_failure_when_detaching_then_operation_is_marked_failed(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_detach_failed_operation",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_detach_failed_operation"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "adapters/failing_duckdb.py": (
                "from typing import Any\n"
                "from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder\n"
                "from sqlbuild.adapter.contract.exceptions import AdapterUserError\n"
                "from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter\n\n"
                "class FailingDuckDbAdapter(DuckDbAdapter):\n"
                "    adapter_name = 'failing_duckdb'\n\n"
                "    def move_or_copy_relation(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        origin: str,\n"
                "        destination: str,\n"
                "        remove_origin: bool,\n"
                "        allow_copy_fallback: bool,\n"
                "        statement_recorder: StatementRecorder,\n"
                "    ) -> None:\n"
                "        raise AdapterUserError('simulated detach copy failure')\n"
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert (
        run_sqb(
            command=("state", "adopt", "--allow-copy"),
            project_dir=project_dir,
            input_text="adopt dev\n",
        ).returncode
        == 0
    )
    (project_dir / "sqlbuild_local.toml").write_text(
        'adapter = "failing_duckdb"\n\n[connection]\ndatabase = "warehouse.duckdb"\n'
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "detach", "--allow-copy"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in (result.stdout + result.stderr)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT status FROM sqlbuild_state.state_operations WHERE operation_id = 'detach:dev'"
        ),
    ) == [("failed",)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT action, status, message FROM sqlbuild_state.state_operation_events "
            "WHERE operation_id = 'detach:dev' ORDER BY created_at"
        ),
    ) == [
        ("start", "running", "starting detach"),
        ("fail", "failed", test_case.expected_error_fragment),
    ]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'dev' AND table_name = 'orders'"
        ),
    ) == [("VIEW",)]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'dev__sqb_physical' AND table_name = 'orders__v_orders'"
        ),
    ) == [("BASE TABLE",)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT status FROM sqlbuild_state.virtual_environments "
            "WHERE virtual_environment_name = 'dev'"
        ),
    ) == [("finalized",)]


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="interrupted adopt records failed operation and leaves recoverable residue",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="simulated adopt failure after move",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_adopt_move_failure_when_adopting_then_operation_is_marked_failed(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_adopt_failed_operation",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_adopt_failed_operation"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "adapters/failing_duckdb.py": (
                "from typing import Any\n"
                "from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder\n"
                "from sqlbuild.adapter.contract.exceptions import AdapterUserError\n"
                "from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter\n\n"
                "class FailingDuckDbAdapter(DuckDbAdapter):\n"
                "    adapter_name = 'failing_duckdb'\n\n"
                "    def move_or_copy_relation(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        origin: str,\n"
                "        destination: str,\n"
                "        remove_origin: bool,\n"
                "        allow_copy_fallback: bool,\n"
                "        statement_recorder: StatementRecorder,\n"
                "    ) -> None:\n"
                "        super().move_or_copy_relation(\n"
                "            connection=connection,\n"
                "            origin=origin,\n"
                "            destination=destination,\n"
                "            remove_origin=remove_origin,\n"
                "            allow_copy_fallback=allow_copy_fallback,\n"
                "            statement_recorder=statement_recorder,\n"
                "        )\n"
                "        raise AdapterUserError('simulated adopt failure after move')\n"
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE SCHEMA dev; CREATE TABLE dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    (project_dir / "sqlbuild_local.toml").write_text(
        'adapter = "failing_duckdb"\n\n'
        "[connection]\n"
        f'database = "{project_dir / "warehouse.duckdb"}"\n'
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt", "--allow-copy"),
        project_dir=project_dir,
        input_text="adopt dev\n",
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in (result.stdout + result.stderr)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT status FROM sqlbuild_state.state_operations WHERE operation_id = 'adopt:dev'",
    ) == [("failed",)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT action, status, message FROM sqlbuild_state.state_operation_events "
            "WHERE operation_id = 'adopt:dev' ORDER BY created_at"
        ),
    ) == [
        ("start", "running", "starting adopt"),
        ("fail", "failed", test_case.expected_error_fragment),
    ]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'dev__sqb_physical' AND table_name = 'orders__v_orders'"
        ),
    ) == [("BASE TABLE",)]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'dev' AND table_name = 'orders'"
        ),
    ) == [(0,)]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type = 'model'"
        ),
    ) == [(0,)]


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="detach recreates view models as views",
            project_toml="",
            expected_exit_code=0,
            expected_error_fragment="VIEW",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_model_when_detaching_then_stateless_target_remains_a_view(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_detach_view_model",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_detach_view_model"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS id\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="CREATE SCHEMA dev; CREATE VIEW dev.orders AS SELECT 1 AS id",
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert (
        run_sqb(
            command=("state", "adopt", "--allow-copy"),
            project_dir=project_dir,
            input_text="adopt dev\n",
        ).returncode
        == test_case.expected_exit_code
    )

    detach_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "detach", "--allow-copy"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )

    assert detach_result.returncode == test_case.expected_exit_code, (
        detach_result.stdout + detach_result.stderr
    )
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev.orders",
    ) == [(1,)]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_type FROM information_schema.tables "
            "WHERE table_schema = 'dev' AND table_name = 'orders'"
        ),
    ) == [(test_case.expected_error_fragment,)]


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="adopt cancels on wrong confirmation",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="cancelled",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_wrong_confirmation_when_adopting_then_it_cancels(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_adopt_cancelled",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_adopt_cancelled"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "adopt"),
        project_dir=project_dir,
        input_text="nope\n",
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "test_case",
    [
        StateModeGuardE2ETestCase(
            description="detach blocks non-finalized virtual environment",
            project_toml="",
            expected_exit_code=1,
            expected_error_fragment="requires a finalized virtual environment",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_non_finalized_virtual_environment_when_detaching_then_it_blocks(
    tmp_path: Path,
    test_case: StateModeGuardE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_state_detach_not_finalized",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_state_detach_not_finalized"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.virtual_environments "
            "(virtual_environment_name, status, created_at, updated_at) "
            "VALUES ('dev', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "detach"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_error_fragment in (result.stdout + result.stderr)


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
    ids=lambda case: case.description,
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
default_target = "dev"

[settings]
virtual_environments = true

[connection]
database = "warehouse.duckdb"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
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
