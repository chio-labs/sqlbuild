from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresStateAdoptDetachE2ETestCase,
    PostgresStateConnectionErrorE2ETestCase,
    PostgresStateExplicitRollbackE2ETestCase,
    PostgresStateLifecycleE2ETestCase,
    PostgresStateLifecycleErrorE2ETestCase,
    PostgresStateLocalOverrideE2ETestCase,
    PostgresStateResetInvalidE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_unique_schema_name,
    cleanup_postgres_state_schemas,
    execute_postgres_sql,
    fetch_postgres_rows,
    quote_identifier,
    quoted_relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)
from tests.e2e.src.sqlbuild.cli.commands.main.state.helpers import (
    assert_state_cli_error,
    build_postgres_local_state_connection_toml,
    build_postgres_state_project_toml,
)

POSTGRES_STATE_LIFECYCLE_ERROR_E2E_TEST_CASES: tuple[
    PostgresStateLifecycleErrorE2ETestCase, ...
] = (
    PostgresStateLifecycleErrorE2ETestCase(
        description="reset blocks when allow reset is false",
        allow_reset=False,
        command=("--no-color", "state", "reset", "--auto-approve"),
        expected_exit_code=1,
        expected_error_fragment=("set `allow_reset = true` under `[environments.<name>.state]`"),
    ),
    PostgresStateLifecycleErrorE2ETestCase(
        description="reset blocks without auto approve",
        allow_reset=True,
        command=("--no-color", "state", "reset"),
        expected_exit_code=1,
        expected_error_fragment="state reset requires --auto-approve",
    ),
    PostgresStateLifecycleErrorE2ETestCase(
        description="rollback blocks before backup exists",
        allow_reset=False,
        command=("--no-color", "state", "rollback"),
        expected_exit_code=1,
        expected_error_fragment="No state backup is available for rollback",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateLifecycleE2ETestCase(
            description="postgres state lifecycle commands manage state tables",
            expected_exit_code=0,
            expected_schema_version=1,
        )
    ],
    ids=["postgres state lifecycle commands manage state tables"],
)
def test_given_postgres_state_config_when_running_state_lifecycle_then_state_store_is_updated(
    test_case: PostgresStateLifecycleE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_project",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_project",
                config=postgres_e2e_config,
                state_schema=state_schema,
                allow_reset=True,
            )
        },
    )

    try:
        init_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "init"),
            project_dir=project_dir,
        )
        assert init_result.returncode == test_case.expected_exit_code, (
            init_result.stdout + init_result.stderr
        )
        assert test_case.expected_init_fragment in init_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT schema_version FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_schema_version,),)

        migrate_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "migrate"),
            project_dir=project_dir,
        )
        assert migrate_result.returncode == test_case.expected_exit_code, (
            migrate_result.stdout + migrate_result.stderr
        )
        assert test_case.expected_migrate_fragment in migrate_result.stdout

        execute_postgres_sql(
            sql=(
                "DELETE FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')}"
            ),
            config=postgres_e2e_config,
        )
        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "rollback"),
            project_dir=project_dir,
        )
        assert rollback_result.returncode == test_case.expected_exit_code, (
            rollback_result.stdout + rollback_result.stderr
        )
        assert test_case.expected_rollback_fragment in rollback_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT schema_version FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_schema_version,),)

        reset_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "reset", "--auto-approve"),
            project_dir=project_dir,
        )
        assert reset_result.returncode == test_case.expected_exit_code, (
            reset_result.stdout + reset_result.stderr
        )
        assert test_case.expected_reset_fragment in reset_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{state_schema}' AND table_name = 'state_versions'"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateAdoptDetachE2ETestCase(
            description="postgres adopt and detach preserve logical table name",
            expected_exit_code=0,
            expected_rows_after_adopt=((1,),),
            expected_rows_after_detach=((1,),),
            expected_detached_status="detached",
        )
    ],
    ids=["postgres adopt and detach preserve logical table name"],
)
def test_given_postgres_virtual_state_when_adopting_and_detaching_then_state_is_detached(
    test_case: PostgresStateAdoptDetachE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_adopt_detach",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_state_adopt_detach"\n'
                'adapter = "postgres"\n'
                'environment_mode = "virtual"\n'
                'default_environment = "dev"\n\n'
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[environments.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[environments.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[environments.dev.state.connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n'
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        execute_postgres_sql(
            sql=(
                f"CREATE SCHEMA {quote_identifier(warehouse_schema)}; "
                f"CREATE TABLE {quoted_relation_name(schema_name=warehouse_schema, name='orders')} "
                "AS SELECT 1 AS id"
            ),
            config=postgres_e2e_config,
        )
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        adopt_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "adopt", "--allow-copy"),
            project_dir=project_dir,
            input_text="adopt dev\n",
        )
        assert adopt_result.returncode == test_case.expected_exit_code, (
            adopt_result.stdout + adopt_result.stderr
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT id FROM "
                    f"{quoted_relation_name(schema_name=warehouse_schema, name='orders')}"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows_after_adopt
        )

        detach_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "detach", "--allow-copy"),
            project_dir=project_dir,
            input_text="detach dev\n",
        )
        assert detach_result.returncode == test_case.expected_exit_code, (
            detach_result.stdout + detach_result.stderr
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT id FROM "
                    f"{quoted_relation_name(schema_name=warehouse_schema, name='orders')}"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows_after_detach
        )
        assert fetch_postgres_rows(
            sql=(
                "SELECT status FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')} "
                "WHERE virtual_environment_name = 'dev'"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_detached_status,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    POSTGRES_STATE_LIFECYCLE_ERROR_E2E_TEST_CASES,
    ids=[case.description for case in POSTGRES_STATE_LIFECYCLE_ERROR_E2E_TEST_CASES],
)
def test_given_postgres_state_config_when_running_blocked_state_command_then_cli_reports_error(
    test_case: PostgresStateLifecycleErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_project",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_project",
                config=postgres_e2e_config,
                state_schema=state_schema,
                allow_reset=test_case.allow_reset,
            )
        },
    )

    try:
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
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateExplicitRollbackE2ETestCase(
            description="postgres rollback accepts explicit backup id",
            expected_exit_code=0,
            expected_schema_version=1,
        )
    ],
    ids=["postgres rollback accepts explicit backup id"],
)
def test_given_postgres_state_backup_when_rolling_back_explicit_backup_id_then_restores_backup(
    test_case: PostgresStateExplicitRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_project",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_project",
                config=postgres_e2e_config,
                state_schema=state_schema,
            )
        },
    )

    try:
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
        events_table: str = quoted_relation_name(
            schema_name=state_schema,
            name="state_migration_events",
        )
        backup_id: str = str(
            fetch_postgres_rows(
                sql=(
                    f"SELECT backup_id FROM {events_table} "
                    "WHERE action = 'backup' ORDER BY created_at DESC LIMIT 1"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        execute_postgres_sql(
            sql=(
                "UPDATE "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')} "
                "SET schema_version = 2"
            ),
            config=postgres_e2e_config,
        )
        second_migrate_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "migrate"),
            project_dir=project_dir,
        )
        assert second_migrate_result.returncode == test_case.expected_exit_code, (
            second_migrate_result.stdout + second_migrate_result.stderr
        )
        execute_postgres_sql(
            sql=(
                "DELETE FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')}"
            ),
            config=postgres_e2e_config,
        )

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "rollback", "--backup-id", backup_id),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code, (
            rollback_result.stdout + rollback_result.stderr
        )
        assert test_case.expected_rollback_fragment in rollback_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT schema_version FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_schema_version,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateLocalOverrideE2ETestCase(
            description="local state connection override controls postgres state database",
            expected_exit_code=0,
            expected_schema_version=1,
        )
    ],
    ids=["local state connection override controls postgres state database"],
)
def test_given_postgres_local_state_override_when_running_state_init_then_cli_uses_local_config(
    test_case: PostgresStateLocalOverrideE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    bad_state_config: dict[str, object] = {**postgres_e2e_config, "port": 1}
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_project",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_project",
                config=postgres_e2e_config,
                state_config=bad_state_config,
                state_schema=state_schema,
            ),
            "sqlbuild_local.toml": build_postgres_local_state_connection_toml(
                config=postgres_e2e_config
            ),
        },
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "init"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert fetch_postgres_rows(
            sql=(
                "SELECT schema_version FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_schema_version,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateConnectionErrorE2ETestCase(
            description="postgres state connection failure renders coded cli error",
            expected_exit_code=1,
            expected_error_fragment="Could not connect to Postgres state backend",
        )
    ],
    ids=["postgres state connection failure renders coded cli error"],
)
def test_given_bad_postgres_state_connection_when_running_state_init_then_cli_reports_error(
    test_case: PostgresStateConnectionErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    bad_state_config: dict[str, object] = {**postgres_e2e_config, "port": 1}
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_project",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_project",
                config=postgres_e2e_config,
                state_config=bad_state_config,
                state_schema=state_schema,
            )
        },
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
        PostgresStateResetInvalidE2ETestCase(
            description="postgres reset makes migrate block until state is initialized again",
            expected_exit_code=1,
            expected_error_fragment="Cannot backup invalid state schema",
        )
    ],
    ids=["postgres reset makes migrate block until state is initialized again"],
)
def test_given_postgres_state_reset_when_running_migrate_then_cli_reports_invalid_state(
    test_case: PostgresStateResetInvalidE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_project",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_project",
                config=postgres_e2e_config,
                state_schema=state_schema,
                allow_reset=True,
            )
        },
    )

    try:
        init_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "init"),
            project_dir=project_dir,
        )
        assert init_result.returncode == 0, init_result.stdout + init_result.stderr
        reset_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "reset", "--auto-approve"),
            project_dir=project_dir,
        )
        assert reset_result.returncode == 0, reset_result.stdout + reset_result.stderr

        migrate_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "migrate"),
            project_dir=project_dir,
        )

        assert_state_cli_error(
            result=migrate_result,
            expected_exit_code=test_case.expected_exit_code,
            expected_error_fragment=test_case.expected_error_fragment,
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
