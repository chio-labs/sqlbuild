from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresJanitorDetachedVdeE2ETestCase,
    PostgresReconcileE2ETestCase,
    PostgresStateAdoptDetachE2ETestCase,
    PostgresStateConnectionErrorE2ETestCase,
    PostgresStateExplicitRollbackE2ETestCase,
    PostgresStateLifecycleE2ETestCase,
    PostgresStateLifecycleErrorE2ETestCase,
    PostgresStateLocalOverrideE2ETestCase,
    PostgresStateResetInvalidE2ETestCase,
    PostgresStateSchemaCorruptionE2ETestCase,
    PostgresVirtualRollbackE2ETestCase,
    PostgresVirtualSeedE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_postgres_virtual_project_toml,
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
    [
        PostgresJanitorDetachedVdeE2ETestCase(
            description="postgres janitor prunes detached VDE refs and physical versions",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion",
                "detached VDEs pruned",
                "Eligible detached VDEs",
                "dev  detached virtual environment",
                "state items",
            ),
            expected_virtual_environment_count_after=0,
            expected_ref_count_after=0,
        )
    ],
    ids=["postgres janitor prunes detached VDE refs and physical versions"],
)
def test_given_postgres_detached_vde_when_running_janitor_then_refs_and_physical_are_pruned(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_detached_vde",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_janitor_detached_vde"\n'
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
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[janitor]\n"
                "enabled = true\n"
                "retention_days = 0\n"
                "delete_tracked_only = false\n"
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
        physical_relation_name: str = str(
            fetch_postgres_rows(
                sql=(
                    "SELECT relation_name FROM "
                    f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                    "WHERE model_name = 'orders'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        detach_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "detach", "--allow-copy"),
            project_dir=project_dir,
            input_text="detach dev\n",
        )
        assert detach_result.returncode == test_case.expected_exit_code, (
            detach_result.stdout + detach_result.stderr
        )

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code, (
            janitor_result.stdout + janitor_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_virtual_environment_count_after,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environment_refs')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_ref_count_after,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                f"AND table_name = '{physical_relation_name}'"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresJanitorDetachedVdeE2ETestCase(
            description="postgres janitor prunes expired non-active VDE",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "expired VDEs pruned",
                "Eligible expired VDEs",
                "pr  expired virtual environment",
                "state items",
            ),
            expected_virtual_environment_count_after=1,
            expected_ref_count_after=1,
        )
    ],
    ids=["postgres janitor prunes expired non-active VDE"],
)
def test_given_postgres_non_active_vde_when_running_janitor_then_it_prunes_expired_environment(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_expired_vde",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_janitor_expired_vde",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            )
            + "\n[janitor]\nenabled = true\nretention_days = 0\ndelete_tracked_only = false\n",
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
            ).returncode
            == 0
        )

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code, (
            janitor_result.stdout + janitor_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_virtual_environment_count_after,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environment_refs')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_ref_count_after,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresJanitorDetachedVdeE2ETestCase(
            description="postgres janitor prunes old state backups and expired locks",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "state backups pruned",
                "expired locks pruned",
                "Eligible state backups",
                "Eligible expired locks",
                "state items",
            ),
            expected_virtual_environment_count_after=1,
            expected_ref_count_after=0,
        )
    ],
    ids=["postgres janitor prunes old state backups and expired locks"],
)
def test_given_postgres_state_backups_and_expired_locks_when_running_janitor_then_state_is_pruned(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_state_cleanup",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_janitor_state_cleanup",
                config=postgres_e2e_config,
                state_schema=state_schema,
            )
            + "\n[janitor]\nenabled = true\nretention_days = 0\ndelete_tracked_only = false\n"
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert (
            run_sqb(command=("--no-color", "state", "migrate"), project_dir=project_dir).returncode
            == 0
        )
        execute_postgres_sql(
            sql=(
                "UPDATE "
                f"{quoted_relation_name(schema_name=state_schema, name='state_versions')} "
                "SET schema_version = 2"
            ),
            config=postgres_e2e_config,
        )
        assert (
            run_sqb(command=("--no-color", "state", "migrate"), project_dir=project_dir).returncode
            == 0
        )
        execute_postgres_sql(
            sql=(
                "INSERT INTO "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')} "
                "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
                "('virtual_env:stale', 'owner', TIMESTAMP '2000-01-01', "
                "TIMESTAMP '2000-01-01', TIMESTAMP '2000-01-01')"
            ),
            config=postgres_e2e_config,
        )

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code, (
            janitor_result.stdout + janitor_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.schemata "
                f"WHERE schema_name LIKE '{state_schema}__backup_%'"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_virtual_environment_count_after,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_ref_count_after,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualRollbackE2ETestCase(
            description="postgres rollback restores previous finalized checkpoint",
            expected_rows=((1,),),
            expected_stdout_fragments=(
                "Virtual rollback complete",
                "virtual environment  dev",
                "status               finalized",
                "rolled back models   1",
            ),
            expected_checkpoint_count=2,
        )
    ],
    ids=["postgres rollback restores previous finalized checkpoint"],
)
def test_given_postgres_finalized_checkpoints_when_rolling_back_then_refs_and_view_restore(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_rollback",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_virtual_rollback"\n'
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
                f'schema = "{state_schema}"\n\n'
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
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        refs_table: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_refs",
        )
        initial_ref_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                "SELECT model_name, version_hash FROM "
                f"{refs_table} "
                "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
            ),
            config=postgres_e2e_config,
        )
        (project_dir / "models" / "orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        checkpoints_table: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_checkpoints",
        )
        checkpoint_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(f"SELECT checkpoint_id FROM {checkpoints_table} ORDER BY created_at"),
            config=postgres_e2e_config,
        )
        assert len(checkpoint_rows) == test_case.expected_checkpoint_count
        checkpoint_id: str = str(checkpoint_rows[0][0])
        list_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "checkpoints", "list"),
            project_dir=project_dir,
        )
        assert list_result.returncode == test_case.expected_exit_code, list_result.stderr
        assert checkpoint_id in list_result.stdout
        show_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "checkpoints", "show", checkpoint_id),
            project_dir=project_dir,
        )
        assert show_result.returncode == test_case.expected_exit_code, show_result.stderr
        assert "orders" in show_result.stdout
        diff_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "checkpoints", "diff", checkpoint_id),
            project_dir=project_dir,
        )
        assert diff_result.returncode == test_case.expected_exit_code, diff_result.stderr
        assert "changed refs     1" in diff_result.stdout

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "rollback"),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code, (
            rollback_result.stdout + rollback_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in rollback_result.stdout
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT model_name, version_hash FROM "
                    f"{refs_table} "
                    "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
                ),
                config=postgres_e2e_config,
            )
            == initial_ref_rows
        )
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        assert (
            fetch_postgres_rows(
                sql=f"SELECT id FROM {logical_relation} ORDER BY id",
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualRollbackE2ETestCase(
            description="postgres rollback blocks when checkpoint physical relation is missing",
            expected_rows=(),
            expected_stdout_fragments=(
                "error[S024]",
                "checkpoint references missing warehouse relation",
            ),
            expected_checkpoint_count=2,
            expected_exit_code=1,
        )
    ],
    ids=["postgres rollback blocks when checkpoint physical relation is missing"],
)
def test_given_postgres_checkpoint_physical_relation_missing_when_rolling_back_then_it_blocks(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_rollback_missing_physical",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_virtual_rollback_missing_physical",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        checkpoints_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_checkpoints",
        )
        checkpoint_refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_checkpoint_refs",
        )
        physical_relations_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="physical_relations",
        )
        checkpoint_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=f"SELECT checkpoint_id FROM {checkpoints_relation}",
            config=postgres_e2e_config,
        )
        assert len(checkpoint_rows) == test_case.expected_checkpoint_count
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                f"SELECT pr.schema_name, pr.relation_name FROM {checkpoints_relation} cp "
                f"JOIN {checkpoint_refs_relation} cr "
                "ON cp.checkpoint_id = cr.checkpoint_id JOIN "
                f"{physical_relations_relation} pr "
                "ON pr.model_name = cr.model_name AND pr.version_hash = cr.version_hash "
                "WHERE cp.virtual_environment_name = 'dev' AND cr.model_name = 'orders' "
                "ORDER BY cp.created_at ASC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]
        missing_relation: str = quoted_relation_name(
            schema_name=str(physical_schema_name),
            name=str(physical_relation_name),
        )
        execute_postgres_sql(
            sql=f"DROP TABLE {missing_relation} CASCADE",
            config=postgres_e2e_config,
        )

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "rollback"),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code
        combined_output: str = rollback_result.stdout + rollback_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in combined_output
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualRollbackE2ETestCase(
            description="postgres rollback blocks when no previous checkpoint exists",
            expected_rows=(),
            expected_stdout_fragments=(
                "error[S021]",
                "no previous finalized checkpoint is available for rollback",
            ),
            expected_checkpoint_count=1,
            expected_exit_code=1,
        )
    ],
    ids=["postgres rollback blocks when no previous checkpoint exists"],
)
def test_given_postgres_only_current_checkpoint_when_rolling_back_then_it_blocks(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_rollback_no_previous",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_virtual_rollback_no_previous",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        checkpoints_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_checkpoints",
        )
        assert (
            len(
                fetch_postgres_rows(
                    sql=f"SELECT checkpoint_id FROM {checkpoints_relation}",
                    config=postgres_e2e_config,
                )
            )
            == test_case.expected_checkpoint_count
        )

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "rollback"),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code
        combined_output: str = rollback_result.stdout + rollback_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in combined_output
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualRollbackE2ETestCase(
            description="postgres rollback blocks when target VDE lock exists",
            expected_rows=(),
            expected_stdout_fragments=("virtual environment 'dev' is locked",),
            expected_checkpoint_count=2,
            expected_exit_code=1,
        )
    ],
    ids=["postgres rollback blocks when target VDE lock exists"],
)
def test_given_postgres_target_virtual_environment_lock_when_rolling_back_then_it_blocks(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_rollback_locked_target",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_virtual_rollback_locked_target",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        execute_postgres_sql(
            sql=(
                "INSERT INTO "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')} "
                "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
                "('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            config=postgres_e2e_config,
        )

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "rollback", "--virtual-env", "dev"),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code
        combined_output: str = rollback_result.stdout + rollback_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in combined_output
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualRollbackE2ETestCase(
            description="postgres checkpoint show blocks for unknown checkpoint",
            expected_rows=(),
            expected_stdout_fragments=("error[C905]", "unknown checkpoint 'missing'"),
            expected_checkpoint_count=1,
            expected_exit_code=1,
        )
    ],
    ids=["postgres checkpoint show blocks for unknown checkpoint"],
)
def test_given_postgres_unknown_checkpoint_when_showing_checkpoint_then_it_blocks(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_checkpoint_unknown",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_virtual_checkpoint_unknown",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "checkpoints", "show", "missing"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code
        combined_output: str = result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in combined_output
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualSeedE2ETestCase(
            description="postgres virtual seeded incremental build uses copy",
            expected_rows=((1, 10), (2, 21), (3, 31)),
            expected_seed_strategy="copy",
        )
    ],
    ids=["postgres virtual seeded incremental build uses copy"],
)
def test_given_postgres_virtual_incremental_change_when_building_then_seeds_with_copy(
    test_case: PostgresVirtualSeedE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_seed")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_seed",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_virtual_seed"\n'
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
                f'schema = "{state_schema}"\n\n'
                "[environments.dev.state.connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                f"    schema: {warehouse_schema}\n"
                "    table: raw_orders\n"
            ),
            "models/orders.sql": (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  cursor ordered_at,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain day,\n"
                "  query_change_backfill bounded-7d\n"
                ");\n\n"
                "SELECT id, ordered_at, amount_cents + 0 AS amount_cents\n"
                'FROM __source("raw_orders")\n'
            ),
        },
    )

    try:
        raw_orders_relation: str = quoted_relation_name(
            schema_name=warehouse_schema,
            name="raw_orders",
        )
        execute_postgres_sql(
            sql=(
                f"CREATE SCHEMA {quote_identifier(warehouse_schema)}; "
                f"CREATE TABLE {raw_orders_relation} "
                "(id INTEGER, ordered_at TIMESTAMP, amount_cents INTEGER); "
                f"INSERT INTO {raw_orders_relation} "
                "VALUES (1, TIMESTAMP '2026-01-01 00:00:00', 10), "
                "(2, TIMESTAMP '2026-01-02 00:00:00', 20)"
            ),
            config=postgres_e2e_config,
        )
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        (project_dir / "models" / "orders.sql").write_text(
            (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  cursor ordered_at,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain day,\n"
                "  query_change_backfill bounded-7d\n"
                ");\n\n"
                "SELECT id, ordered_at, amount_cents + 1 AS amount_cents\n"
                'FROM __source("raw_orders")\n'
            ),
            encoding="utf-8",
        )
        execute_postgres_sql(
            sql=(
                f"INSERT INTO {raw_orders_relation} VALUES (3, TIMESTAMP '2026-01-03 00:00:00', 30)"
            ),
            config=postgres_e2e_config,
        )

        build_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--start-cursor-ts",
                "2026-01-02T00:00:00",
                "--end-cursor-ts",
                "2026-01-04T00:00:00",
            ),
            project_dir=project_dir,
        )

        assert build_result.returncode == test_case.expected_exit_code, (
            build_result.stdout + build_result.stderr
        )
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        assert (
            fetch_postgres_rows(
                sql=f"SELECT id, amount_cents FROM {logical_relation} ORDER BY id",
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
        ancestry_table: str = quoted_relation_name(
            schema_name=state_schema,
            name="physical_relation_ancestry",
        )
        assert fetch_postgres_rows(
            sql=(f"SELECT seed_strategy FROM {ancestry_table} WHERE model_name = 'orders'"),
            config=postgres_e2e_config,
        ) == ((test_case.expected_seed_strategy,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres reconcile repair-view recreates logical view",
            expected_rows=((1,),),
            expected_stdout_fragments=(
                "Repair",
                "model   orders",
                "VDE     dev",
                "action  recreate logical view from state",
                "result  repaired",
            ),
        )
    ],
    ids=["postgres reconcile repair-view recreates logical view"],
)
def test_given_postgres_missing_logical_view_when_repairing_then_view_is_recreated(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_repair",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_reconcile_repair"\n'
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
                f'schema = "{state_schema}"\n\n'
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
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        execute_postgres_sql(
            sql=f"DROP VIEW {logical_relation}",
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        assert (
            fetch_postgres_rows(
                sql=f"SELECT id FROM {logical_relation} ORDER BY id",
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres reconcile attach rebinds logical view",
            expected_rows=((2,),),
            expected_stdout_fragments=("Attach", "model     orders", "result    attached"),
        )
    ],
    ids=["postgres reconcile attach rebinds logical view"],
)
def test_given_postgres_tracked_physical_relation_when_attaching_then_view_is_rebound(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_attach",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_reconcile_attach"\n'
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
                f'schema = "{state_schema}"\n\n'
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
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode
            == test_case.expected_exit_code
        )
        (project_dir / "models" / "orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr"),
                project_dir=project_dir,
            ).returncode
            == test_case.expected_exit_code
        )
        _database_name, physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT database_name, schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE model_name = 'orders' ORDER BY updated_at DESC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]
        physical_relation: str = quoted_relation_name(
            schema_name=str(physical_schema_name),
            name=str(physical_relation_name),
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                physical_relation,
                "--auto-approve",
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        assert (
            fetch_postgres_rows(
                sql=(f"SELECT id FROM {logical_relation} ORDER BY id"),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres reconcile repair-view blocks missing physical relation",
            expected_rows=(),
            expected_stdout_fragments=(
                "missing physical relation: orders",
                "error[C252]: missing physical relation for 'orders'",
            ),
            expected_exit_code=1,
        )
    ],
    ids=["postgres reconcile repair-view blocks missing physical relation"],
)
def test_given_postgres_missing_physical_relation_when_repairing_then_it_blocks(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_missing_physical",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_missing_physical",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE model_name = 'orders' ORDER BY updated_at DESC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]
        missing_relation: str = quoted_relation_name(
            schema_name=str(physical_schema_name),
            name=str(physical_relation_name),
        )
        execute_postgres_sql(
            sql=f"DROP TABLE {missing_relation} CASCADE",
            config=postgres_e2e_config,
        )

        report_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "reconcile", "--virtual-env", "dev"),
            project_dir=project_dir,
        )
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
            ),
            project_dir=project_dir,
        )

        combined_output: str = (
            report_result.stdout + report_result.stderr + result.stdout + result.stderr
        )
        assert result.returncode == test_case.expected_exit_code, combined_output
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in combined_output
        assert "Traceback" not in combined_output
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres reconcile attach blocks untracked physical relation",
            expected_rows=(),
            expected_stdout_fragments=("is not a tracked relation",),
            expected_exit_code=1,
        )
    ],
    ids=["postgres reconcile attach blocks untracked physical relation"],
)
def test_given_postgres_untracked_physical_relation_when_attaching_then_it_blocks(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_attach_untracked",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_attach_untracked",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        physical_schema: str = f"{warehouse_schema}__sqb_physical"
        untracked_relation: str = quoted_relation_name(
            schema_name=physical_schema,
            name="untracked_orders",
        )
        execute_postgres_sql(
            sql=f"CREATE TABLE {untracked_relation} AS SELECT 9 AS id",
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--auto-approve",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                untracked_relation,
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres reconcile attach blocks wrong-model tracked physical relation",
            expected_rows=(),
            expected_stdout_fragments=("is not a tracked relation for 'orders'",),
            expected_exit_code=1,
        )
    ],
    ids=["postgres reconcile attach blocks wrong-model tracked physical relation"],
)
def test_given_postgres_wrong_model_physical_relation_when_attaching_then_refs_are_unchanged(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_attach_wrong_model",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_attach_wrong_model",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
            "models/customers.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE model_name = 'customers' ORDER BY updated_at DESC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--auto-approve",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                quoted_relation_name(
                    schema_name=str(physical_schema_name),
                    name=str(physical_relation_name),
                ),
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
        assert (
            fetch_postgres_rows(
                sql=(
                    f"SELECT version_hash FROM {refs_relation} "
                    "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
                ),
                config=postgres_e2e_config,
            )
            == original_refs
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres reconcile attach cancellation leaves refs unchanged",
            expected_rows=(),
            expected_stdout_fragments=("reconcile attach cancelled",),
            expected_exit_code=1,
            input_text="nope\n",
        )
    ],
    ids=["postgres reconcile attach cancellation leaves refs unchanged"],
)
def test_given_postgres_wrong_confirmation_when_attaching_then_refs_are_unchanged(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_attach_cancelled",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_attach_cancelled",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE model_name = 'orders' ORDER BY updated_at DESC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                quoted_relation_name(
                    schema_name=str(physical_schema_name),
                    name=str(physical_relation_name),
                ),
            ),
            project_dir=project_dir,
            input_text=test_case.input_text,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
        assert (
            fetch_postgres_rows(
                sql=(
                    f"SELECT version_hash FROM {refs_relation} "
                    "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
                ),
                config=postgres_e2e_config,
            )
            == original_refs
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres repair-view blocks logical target table",
            expected_rows=(),
            expected_stdout_fragments=("logical target for 'orders' is a table",),
            expected_exit_code=1,
        )
    ],
    ids=["postgres repair-view blocks logical target table"],
)
def test_given_postgres_logical_target_table_when_repairing_then_it_blocks(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_repair_table_block",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_repair_table_block",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        execute_postgres_sql(
            sql=f"DROP VIEW {logical_relation}; CREATE TABLE {logical_relation} AS SELECT 1 AS id",
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres attach blocks logical target table before ref update",
            expected_rows=(),
            expected_stdout_fragments=("logical target for 'orders' is a table",),
            expected_exit_code=1,
        )
    ],
    ids=["postgres attach blocks logical target table before ref update"],
)
def test_given_postgres_logical_target_table_when_attaching_then_refs_are_unchanged(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_attach_table_block",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_attach_table_block",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE model_name = 'orders' ORDER BY updated_at DESC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        execute_postgres_sql(
            sql=f"DROP VIEW {logical_relation}; CREATE TABLE {logical_relation} AS SELECT 1 AS id",
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--auto-approve",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                quoted_relation_name(
                    schema_name=str(physical_schema_name),
                    name=str(physical_relation_name),
                ),
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
        assert (
            fetch_postgres_rows(
                sql=(
                    f"SELECT version_hash FROM {refs_relation} "
                    "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
                ),
                config=postgres_e2e_config,
            )
            == original_refs
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres repair-view blocks when target vde is locked",
            expected_rows=(),
            expected_stdout_fragments=("virtual environment 'dev' is locked",),
            expected_exit_code=1,
        )
    ],
    ids=["postgres repair-view blocks when target vde is locked"],
)
def test_given_postgres_target_virtual_environment_lock_when_repairing_then_it_blocks(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_repair_locked",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_repair_locked",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="orders",
        )
        execute_postgres_sql(
            sql=f"DROP VIEW {logical_relation}",
            config=postgres_e2e_config,
        )
        execute_postgres_sql(
            sql=(
                "INSERT INTO "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')} "
                "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
                "('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__dev' AND table_name = 'orders'"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresReconcileE2ETestCase(
            description="postgres attach blocks when target vde is locked",
            expected_rows=(),
            expected_stdout_fragments=("virtual environment 'dev' is locked",),
            expected_exit_code=1,
        )
    ],
    ids=["postgres attach blocks when target vde is locked"],
)
def test_given_postgres_target_virtual_environment_lock_when_attaching_then_refs_are_unchanged(
    test_case: PostgresReconcileE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_reconcile_attach_locked",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_reconcile_attach_locked",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE model_name = 'orders' ORDER BY updated_at DESC LIMIT 1"
            ),
            config=postgres_e2e_config,
        )[0]
        execute_postgres_sql(
            sql=(
                "INSERT INTO "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')} "
                "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
                "('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "reconcile",
                "attach",
                "--auto-approve",
                "--virtual-env",
                "dev",
                "--model",
                "orders",
                "--physical-relation",
                quoted_relation_name(
                    schema_name=str(physical_schema_name),
                    name=str(physical_relation_name),
                ),
            ),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout + result.stderr
        assert (
            fetch_postgres_rows(
                sql=(
                    f"SELECT version_hash FROM {refs_relation} "
                    "WHERE virtual_environment_name = 'dev' AND model_name = 'orders'"
                ),
                config=postgres_e2e_config,
            )
            == original_refs
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


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


POSTGRES_STATE_SCHEMA_CORRUPTION_E2E_TEST_CASES: tuple[
    PostgresStateSchemaCorruptionE2ETestCase, ...
] = (
    PostgresStateSchemaCorruptionE2ETestCase(
        description="postgres migrate blocks cleanly when required state table is missing",
        mutation_sql_template="DROP TABLE {virtual_environment_refs}",
        expected_exit_code=1,
        expected_error_fragment="Cannot backup invalid state schema",
    ),
    PostgresStateSchemaCorruptionE2ETestCase(
        description="postgres migrate blocks cleanly when required state column is missing",
        mutation_sql_template='ALTER TABLE {state_versions} DROP COLUMN "updated_at"',
        expected_exit_code=1,
        expected_error_fragment="Cannot backup invalid state schema",
    ),
    PostgresStateSchemaCorruptionE2ETestCase(
        description="postgres migrate blocks cleanly when required state column has wrong type",
        mutation_sql_template=(
            'ALTER TABLE {state_versions} ALTER COLUMN "schema_version" '
            'TYPE text USING "schema_version"::text'
        ),
        expected_exit_code=1,
        expected_error_fragment="Cannot backup invalid state schema",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    POSTGRES_STATE_SCHEMA_CORRUPTION_E2E_TEST_CASES,
    ids=[case.description for case in POSTGRES_STATE_SCHEMA_CORRUPTION_E2E_TEST_CASES],
)
def test_given_corrupt_postgres_state_schema_when_migrating_then_cli_blocks_cleanly(
    test_case: PostgresStateSchemaCorruptionE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_schema_corruption",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_schema_corruption",
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
        assert init_result.returncode == 0, init_result.stdout + init_result.stderr
        execute_postgres_sql(
            sql=test_case.mutation_sql_template.format(
                state_versions=quoted_relation_name(
                    schema_name=state_schema,
                    name="state_versions",
                ),
                virtual_environment_refs=quoted_relation_name(
                    schema_name=state_schema,
                    name="virtual_environment_refs",
                ),
            ),
            config=postgres_e2e_config,
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
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateResetInvalidE2ETestCase(
            description="postgres explicit rollback blocks cleanly when backup schema is deleted",
            expected_exit_code=1,
            expected_error_fragment="backup_",
        )
    ],
    ids=["postgres explicit rollback blocks cleanly when backup schema is deleted"],
)
def test_given_deleted_postgres_state_backup_when_rolling_back_then_it_blocks_cleanly(
    test_case: PostgresStateResetInvalidE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_deleted_backup",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_deleted_backup",
                config=postgres_e2e_config,
                state_schema=state_schema,
            )
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert (
            run_sqb(command=("--no-color", "state", "migrate"), project_dir=project_dir).returncode
            == 0
        )
        events_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="state_migration_events",
        )
        backup_id: str = str(
            fetch_postgres_rows(
                sql=(
                    f"SELECT backup_id FROM {events_relation} "
                    "WHERE action = 'backup' ORDER BY created_at DESC LIMIT 1"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        execute_postgres_sql(
            sql=f"DROP SCHEMA {quote_identifier(f'{state_schema}__backup_{backup_id}')} CASCADE",
            config=postgres_e2e_config,
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
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateResetInvalidE2ETestCase(
            description="postgres latest rollback blocks cleanly when backup schema is deleted",
            expected_exit_code=1,
            expected_error_fragment="No state backup is available for rollback",
        )
    ],
    ids=["postgres latest rollback blocks cleanly when backup schema is deleted"],
)
def test_given_deleted_latest_postgres_state_backup_when_rolling_back_then_it_blocks_cleanly(
    test_case: PostgresStateResetInvalidE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_state_deleted_latest_backup",
        repo_files={
            "sqlbuild_project.toml": build_postgres_state_project_toml(
                project_name="postgres_state_deleted_latest_backup",
                config=postgres_e2e_config,
                state_schema=state_schema,
            )
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert (
            run_sqb(command=("--no-color", "state", "migrate"), project_dir=project_dir).returncode
            == 0
        )
        events_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="state_migration_events",
        )
        backup_id: str = str(
            fetch_postgres_rows(
                sql=(
                    f"SELECT backup_id FROM {events_relation} "
                    "WHERE action = 'backup' ORDER BY created_at DESC LIMIT 1"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        execute_postgres_sql(
            sql=f"DROP SCHEMA {quote_identifier(f'{state_schema}__backup_{backup_id}')} CASCADE",
            config=postgres_e2e_config,
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
