from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresJanitorDetachedVdeE2ETestCase,
    PostgresReconcileE2ETestCase,
    PostgresStateAdoptDetachE2ETestCase,
    PostgresStateAdoptDetachErrorE2ETestCase,
    PostgresStateConnectionErrorE2ETestCase,
    PostgresStateExplicitRollbackE2ETestCase,
    PostgresStateLifecycleE2ETestCase,
    PostgresStateLifecycleErrorE2ETestCase,
    PostgresStateLocalOverrideE2ETestCase,
    PostgresStateResetInvalidE2ETestCase,
    PostgresStateSchemaCorruptionE2ETestCase,
    PostgresVirtualParityE2ETestCase,
    PostgresVirtualRollbackE2ETestCase,
    PostgresVirtualSeedE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_postgres_virtual_clone_project_toml,
    build_postgres_virtual_plan_repo_files,
    build_postgres_virtual_project_toml,
    build_unique_schema_name,
    cleanup_postgres_state_schemas,
    execute_postgres_sql,
    fetch_postgres_rows,
    quote_identifier,
    quoted_relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.main.state.helpers import (
    assert_state_cli_error,
    build_postgres_local_state_connection_toml,
    build_postgres_state_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[targets.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
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
            command=("--no-color", "state", "adopt"),
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
        PostgresStateAdoptDetachErrorE2ETestCase(
            description="postgres adopt blocks without unsuffixed virtual env",
            expected_exit_code=1,
            expected_error_fragment="unsuffixed_virtual_env",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_missing_unsuffixed_virtual_env_when_adopting_then_it_blocks(
    test_case: PostgresStateAdoptDetachErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_adopt_missing_unsuffixed",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_adopt_missing_unsuffixed",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
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
            == 0
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "adopt"),
            project_dir=project_dir,
            input_text="adopt dev\n",
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_error_fragment in (result.stdout + result.stderr)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateAdoptDetachErrorE2ETestCase(
            description="postgres adopt blocks view copy fallback without explicit permission",
            expected_exit_code=1,
            expected_error_fragment="requires --allow-copy",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_copy_fallback_required_when_adopting_without_allow_copy_then_it_blocks(
    test_case: PostgresStateAdoptDetachErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_adopt_allow_copy_required",
        repo_files={
            "sqlbuild_project.toml": (
                build_postgres_virtual_project_toml(
                    project_name="postgres_adopt_allow_copy_required",
                    config=postgres_e2e_config,
                    state_schema=state_schema,
                    warehouse_schema=warehouse_schema,
                    unsuffixed_virtual_env="dev",
                )
            ),
            "models/orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS id\n",
        },
    )

    try:
        execute_postgres_sql(
            sql=(
                f"CREATE SCHEMA {quote_identifier(warehouse_schema)}; "
                f"CREATE VIEW {quoted_relation_name(schema_name=warehouse_schema, name='orders')} "
                "AS SELECT 1 AS id"
            ),
            config=postgres_e2e_config,
        )
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "adopt"),
            project_dir=project_dir,
            input_text="adopt dev\n",
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_error_fragment in (result.stdout + result.stderr)
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
        PostgresStateAdoptDetachErrorE2ETestCase(
            description="postgres interrupted detach records failed operation",
            expected_exit_code=1,
            expected_error_fragment="simulated detach copy failure",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_detach_copy_failure_when_detaching_then_operation_is_marked_failed(
    test_case: PostgresStateAdoptDetachErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_detach_failed_operation",
        repo_files={
            "sqlbuild_project.toml": (
                build_postgres_virtual_project_toml(
                    project_name="postgres_detach_failed_operation",
                    config=postgres_e2e_config,
                    state_schema=state_schema,
                    warehouse_schema=warehouse_schema,
                    unsuffixed_virtual_env="dev",
                )
            ),
            "sqlbuild_local.toml": "",
            "adapters/failing_postgres.py": (
                "from typing import Any\n"
                "from sqlbuild.adapter.classes.statement_recorder import StatementRecorder\n"
                "from sqlbuild.adapter.exceptions import AdapterUserError\n"
                "from sqlbuild.adapters.postgres.client import PostgresAdapter\n\n"
                "class FailingPostgresAdapter(PostgresAdapter):\n"
                "    adapter_name = 'failing_postgres'\n\n"
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
            == 0
        )
        assert (
            run_sqb(
                command=("--no-color", "state", "adopt", "--allow-copy"),
                project_dir=project_dir,
                input_text="adopt dev\n",
            ).returncode
            == 0
        )
        (project_dir / "sqlbuild_local.toml").write_text('adapter = "failing_postgres"\n')

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "detach", "--allow-copy"),
            project_dir=project_dir,
            input_text="detach dev\n",
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_error_fragment in (result.stdout + result.stderr)
        assert fetch_postgres_rows(
            sql=(
                "SELECT status FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_operations')} "
                "WHERE operation_id = 'detach:dev'"
            ),
            config=postgres_e2e_config,
        ) == (("failed",),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT action, status, message FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='state_operation_events')} "
                "WHERE operation_id = 'detach:dev' ORDER BY created_at"
            ),
            config=postgres_e2e_config,
        ) == (
            ("start", "running", "starting detach"),
            ("fail", "failed", test_case.expected_error_fragment),
        )
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}' AND table_name = 'orders'"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)
        physical_relation_name: str = str(
            fetch_postgres_rows(
                sql=(
                    "SELECT relation_name FROM "
                    f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                    "WHERE artifact_type = 'model' AND artifact_name = 'orders'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        assert fetch_postgres_rows(
            sql=(
                "SELECT table_type FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                f"AND table_name = '{physical_relation_name}'"
            ),
            config=postgres_e2e_config,
        ) == (("BASE TABLE",),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT status FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')} "
                "WHERE virtual_environment_name = 'dev'"
            ),
            config=postgres_e2e_config,
        ) == (("finalized",),)
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
        PostgresStateAdoptDetachErrorE2ETestCase(
            description="postgres detach recreates view models as views",
            expected_exit_code=0,
            expected_error_fragment="VIEW",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_view_model_when_detaching_then_stateless_target_remains_a_view(
    test_case: PostgresStateAdoptDetachErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_detach_view_model",
        repo_files={
            "sqlbuild_project.toml": (
                build_postgres_virtual_project_toml(
                    project_name="postgres_detach_view_model",
                    config=postgres_e2e_config,
                    state_schema=state_schema,
                    warehouse_schema=warehouse_schema,
                    unsuffixed_virtual_env="dev",
                )
            ),
            "models/orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS id\n",
        },
    )

    try:
        execute_postgres_sql(
            sql=(
                f"CREATE SCHEMA {quote_identifier(warehouse_schema)}; "
                f"CREATE VIEW {quoted_relation_name(schema_name=warehouse_schema, name='orders')} "
                "AS SELECT 1 AS id"
            ),
            config=postgres_e2e_config,
        )
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert (
            run_sqb(
                command=("--no-color", "state", "adopt", "--allow-copy"),
                project_dir=project_dir,
                input_text="adopt dev\n",
            ).returncode
            == test_case.expected_exit_code
        )

        detach_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "detach", "--allow-copy"),
            project_dir=project_dir,
            input_text="detach dev\n",
        )

        assert detach_result.returncode == test_case.expected_exit_code, (
            detach_result.stdout + detach_result.stderr
        )
        assert fetch_postgres_rows(
            sql=(
                "SELECT id FROM "
                f"{quoted_relation_name(schema_name=warehouse_schema, name='orders')}"
            ),
            config=postgres_e2e_config,
        ) == ((1,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT table_type FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}' AND table_name = 'orders'"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_error_fragment,),)
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
        PostgresStateAdoptDetachErrorE2ETestCase(
            description="postgres adopt cancels on wrong confirmation",
            expected_exit_code=1,
            expected_error_fragment="cancelled",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_wrong_confirmation_when_adopting_then_it_cancels(
    test_case: PostgresStateAdoptDetachErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_adopt_cancelled",
        repo_files={
            "sqlbuild_project.toml": (
                build_postgres_virtual_project_toml(
                    project_name="postgres_adopt_cancelled",
                    config=postgres_e2e_config,
                    state_schema=state_schema,
                    warehouse_schema=warehouse_schema,
                    unsuffixed_virtual_env="dev",
                )
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
            == 0
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "adopt", "--allow-copy"),
            project_dir=project_dir,
            input_text="nope\n",
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_error_fragment in (result.stdout + result.stderr)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateAdoptDetachErrorE2ETestCase(
            description="postgres detach blocks non-finalized virtual environment",
            expected_exit_code=1,
            expected_error_fragment="requires a finalized virtual environment",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_non_finalized_virtual_environment_when_detaching_then_it_blocks(
    test_case: PostgresStateAdoptDetachErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_detach_not_finalized",
        repo_files={
            "sqlbuild_project.toml": (
                build_postgres_virtual_project_toml(
                    project_name="postgres_detach_not_finalized",
                    config=postgres_e2e_config,
                    state_schema=state_schema,
                    warehouse_schema=warehouse_schema,
                    unsuffixed_virtual_env="dev",
                )
            ),
            "models/orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        execute_postgres_sql(
            sql=(
                "INSERT INTO "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')} "
                "(virtual_environment_name, status, created_at, updated_at) "
                "VALUES ('dev', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            config=postgres_e2e_config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "state", "detach"),
            project_dir=project_dir,
            input_text="detach dev\n",
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_error_fragment in (result.stdout + result.stderr)
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
    ids=lambda case: case.description,
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
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[targets.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n'
                'unsuffixed_virtual_env = "dev"\n\n'
                "[targets.dev.state.connection]\n"
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
                    "WHERE artifact_type = 'model' AND artifact_name = 'orders'"
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
        model_ref_table_name: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_node_refs",
        )
        assert fetch_postgres_rows(
            sql=(f"SELECT COUNT(*) FROM {model_ref_table_name}"),
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
            description="postgres janitor prunes detached VDE after positive retention",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "7 days",
                "detached VDEs pruned",
                "Eligible detached VDEs",
                "dev  detached virtual environment",
                "state items",
            ),
            expected_virtual_environment_count_after=0,
            expected_ref_count_after=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_old_detached_vde_when_running_janitor_then_retention_allows_cleanup(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_detached_retention",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_janitor_detached_retention",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
                unsuffixed_virtual_env="dev",
            )
            + "\n[janitor]\nenabled = true\nretention_days = 7\ndelete_tracked_only = false\n",
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
            == 0
        )
        assert (
            run_sqb(
                command=("--no-color", "state", "adopt", "--allow-copy"),
                project_dir=project_dir,
                input_text="adopt dev\n",
            ).returncode
            == 0
        )
        assert (
            run_sqb(
                command=("--no-color", "state", "detach", "--allow-copy"),
                project_dir=project_dir,
                input_text="detach dev\n",
            ).returncode
            == 0
        )
        execute_postgres_sql(
            sql=(
                "UPDATE "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')} "
                "SET updated_at = TIMESTAMP '2026-01-01' "
                "WHERE virtual_environment_name = 'dev'"
            ),
            config=postgres_e2e_config,
        )

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code, janitor_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')}"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_virtual_environment_count_after,),)
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
    ids=lambda case: case.description,
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
        model_ref_table_name: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_node_refs",
        )
        assert fetch_postgres_rows(
            sql=(f"SELECT COUNT(*) FROM {model_ref_table_name}"),
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
    ids=lambda case: case.description,
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
        PostgresJanitorDetachedVdeE2ETestCase(
            description="postgres janitor skips state cleanup when warehouse cleanup fails",
            expected_exit_code=1,
            expected_stdout_fragments=("simulated janitor drop failure",),
            expected_virtual_environment_count_after=1,
            expected_ref_count_after=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_warehouse_cleanup_failure_when_janitor_then_state_cleanup_is_skipped(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_e2e")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_warehouse_failure",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_janitor_warehouse_failure",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            )
            + "\n[janitor]\nenabled = true\nretention_days = 0\ndelete_tracked_only = false\n",
            "sqlbuild_local.toml": "",
            "adapters/failing_janitor_postgres.py": (
                "from typing import Any\n"
                "from sqlbuild.adapter.exceptions import AdapterUserError\n"
                "from sqlbuild.adapter.classes.statement_recorder import StatementRecorder\n"
                "from sqlbuild.adapters.postgres.client import PostgresAdapter\n\n"
                "class FailingJanitorPostgresAdapter(PostgresAdapter):\n"
                "    adapter_name = 'failing_janitor_postgres'\n\n"
                "    def drop(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        destination: str,\n"
                "        if_exists: bool = True,\n"
                "        statement_recorder: StatementRecorder,\n"
                "    ) -> None:\n"
                "        raise AdapterUserError('simulated janitor drop failure')\n\n"
                "    def drop_view(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        destination: str,\n"
                "        if_exists: bool = True,\n"
                "        statement_recorder: StatementRecorder,\n"
                "    ) -> None:\n"
                "        raise AdapterUserError('simulated janitor drop failure')\n"
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
        (project_dir / "models" / "orders.sql").write_text("MODEL ();\n\nSELECT 2 AS id\n")
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr"),
                project_dir=project_dir,
            ).returncode
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
        (project_dir / "sqlbuild_local.toml").write_text('adapter = "failing_janitor_postgres"\n')

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code
        combined_output: str = janitor_result.stdout + janitor_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in combined_output
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='virtual_environments')} "
                "WHERE virtual_environment_name = 'pr'"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_virtual_environment_count_after,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')} "
                "WHERE lock_key = 'virtual_env:stale'"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_ref_count_after,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresJanitorDetachedVdeE2ETestCase(
            description="postgres janitor prunes old checkpoints and newly unprotected physicals",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "checkpoints pruned",
                "Eligible checkpoints",
                "Deleted ",
                "2 checkpoints.",
            ),
            expected_virtual_environment_count_after=1,
            expected_ref_count_after=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_checkpoints_over_limit_when_running_janitor_then_it_prunes_old_history(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_janitor")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_checkpoint_retention",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_janitor_checkpoint_retention",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 1 AS id",
            extra_project_toml=(
                "\n[janitor]\n"
                "enabled = true\n"
                "retention_days = 0\n"
                "max_checkpoints = 1\n"
                "delete_tracked_only = false\n"
            ),
        ),
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_node_refs",
        )
        physical_relations_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="physical_relations",
        )
        checkpoints_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_checkpoints",
        )
        first_relation_name: str = str(
            fetch_postgres_rows(
                sql=(
                    "SELECT physical_relations.relation_name FROM "
                    f"{refs_relation} AS refs JOIN "
                    f"{physical_relations_relation} AS physical_relations "
                    "ON physical_relations.artifact_type = 'model' "
                    "AND physical_relations.artifact_name = refs.node_name "
                    "AND physical_relations.version_hash = refs.version_hash "
                    "WHERE refs.virtual_environment_name = 'dev' "
                    "AND refs.node_type = 'model' AND refs.node_name = 'stg_orders'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        (project_dir / "models" / "stg_orders.sql").write_text("MODEL ();\n\nSELECT 2 AS id\n")
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "stg_orders.sql").write_text("MODEL ();\n\nSELECT 3 AS id\n")
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        latest_relation_name: str = str(
            fetch_postgres_rows(
                sql=(
                    "SELECT physical_relations.relation_name FROM "
                    f"{refs_relation} AS refs JOIN "
                    f"{physical_relations_relation} AS physical_relations "
                    "ON physical_relations.artifact_type = 'model' "
                    "AND physical_relations.artifact_name = refs.node_name "
                    "AND physical_relations.version_hash = refs.version_hash "
                    "WHERE refs.virtual_environment_name = 'dev' "
                    "AND refs.node_type = 'model' AND refs.node_name = 'stg_orders'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        assert fetch_postgres_rows(
            sql=f"SELECT COUNT(*) FROM {checkpoints_relation}",
            config=postgres_e2e_config,
        ) == ((test_case.expected_ref_count_after,),)

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code, janitor_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert fetch_postgres_rows(
            sql=f"SELECT COUNT(*) FROM {checkpoints_relation}",
            config=postgres_e2e_config,
        ) == ((test_case.expected_virtual_environment_count_after,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                f"AND table_name = '{first_relation_name}'"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                f"AND table_name = '{latest_relation_name}'"
            ),
            config=postgres_e2e_config,
        ) == ((1,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical", config=postgres_e2e_config
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresJanitorDetachedVdeE2ETestCase(
            description="postgres janitor preserves active VDE refs",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "eligible for deletion  0",
                "relation is referenced by an active or retained virtual environment",
            ),
            expected_virtual_environment_count_after=1,
            expected_ref_count_after=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_active_vde_ref_when_running_janitor_then_it_preserves_physical_version(
    test_case: PostgresJanitorDetachedVdeE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_janitor")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_active_ref",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_janitor_active_ref",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 1 AS id",
            extra_project_toml=(
                "\n[janitor]\nenabled = true\nretention_days = 0\ndelete_tracked_only = false\n"
            ),
        ),
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert (
            run_sqb(
                command=("--no-color", "build", "--select", "stg_orders"),
                project_dir=project_dir,
            ).returncode
            == 0
        )
        protected_relation_name: str = str(
            fetch_postgres_rows(
                sql=(
                    "SELECT relation_name FROM "
                    f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                    "WHERE artifact_type = 'model' AND artifact_name = 'stg_orders'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )

        janitor_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve"),
            project_dir=project_dir,
        )

        assert janitor_result.returncode == test_case.expected_exit_code, janitor_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in janitor_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                f"AND table_name = '{protected_relation_name}'"
            ),
            config=postgres_e2e_config,
        ) == ((test_case.expected_ref_count_after,),)
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical", config=postgres_e2e_config
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateLifecycleErrorE2ETestCase(
            description="postgres tracked-only janitor requires query tracking",
            allow_reset=False,
            command=("--no-color", "janitor", "--auto-approve"),
            expected_exit_code=1,
            expected_error_fragment="janitor.delete_tracked_only requires",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_query_tracking_disabled_when_running_tracked_only_janitor_then_it_errors(
    test_case: PostgresStateLifecycleErrorE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_janitor")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_janitor_invalid_config",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_janitor_invalid_config",
                config=postgres_e2e_config,
                state_schema=state_schema,
                warehouse_schema=warehouse_schema,
            ).replace(
                "virtual_environments = true\n",
                "virtual_environments = true\nquery_change_tracking = false\n",
            )
            + "\n[janitor]\nenabled = true\n"
        },
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_error_fragment in result.stderr
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)


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
    ids=lambda case: case.description,
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
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[targets.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n\n'
                "[targets.dev.state.connection]\n"
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
            name="virtual_environment_node_refs",
        )
        initial_ref_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                "SELECT node_name, version_hash FROM "
                f"{refs_table} "
                "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
                "ORDER BY node_name"
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
                    "SELECT node_name, version_hash FROM "
                    f"{refs_table} "
                    "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
                    "ORDER BY node_name"
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
    ids=lambda case: case.description,
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
        checkpoint_model_refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_checkpoint_model_refs",
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
                f"JOIN {checkpoint_model_refs_relation} cr "
                "ON cp.checkpoint_id = cr.checkpoint_id JOIN "
                f"{physical_relations_relation} pr "
                "ON pr.artifact_type = 'model' AND pr.artifact_name = cr.model_name "
                "AND pr.version_hash = cr.version_hash "
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
        PostgresVirtualRollbackE2ETestCase(
            description="postgres partial rollback requires override and marks VDE working",
            expected_rows=((1,),),
            expected_stdout_fragments=(
                "rollback would leave target virtual environment working",
                "status               active",
                "rolled back models   1",
            ),
            expected_checkpoint_count=2,
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_partial_rollback_when_allowed_then_it_marks_vde_working(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_rollback_partial",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_virtual_rollback_partial",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 1 AS id",
        ),
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "stg_orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
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

        blocked_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "rollback", "--select", "stg_orders"),
            project_dir=project_dir,
        )
        assert blocked_result.returncode == 1
        assert test_case.expected_stdout_fragments[0] in blocked_result.stderr

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "rollback",
                "--select",
                "stg_orders",
                "--allow-partial-rollback",
            ),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code, rollback_result.stderr
        for fragment in test_case.expected_stdout_fragments[1:]:
            assert fragment in rollback_result.stdout
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="stg_orders",
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
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical", config=postgres_e2e_config
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualRollbackE2ETestCase(
            description="postgres partial rollback can include stale required upstreams",
            expected_rows=((1,),),
            expected_stdout_fragments=(
                "selected rollback scope is missing stale required upstream models",
                "stg_orders",
                "status               finalized",
                "rolled back models   2",
            ),
            expected_checkpoint_count=2,
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_partial_rollback_missing_stale_upstreams_when_including_then_succeeds(
    test_case: PostgresVirtualRollbackE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_rollback")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_rollback_include_stale",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_virtual_rollback_include_stale",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 1 AS id",
        ),
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "stg_orders.sql").write_text(
            "MODEL ();\n\nSELECT 2 AS id\n",
            encoding="utf-8",
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

        blocked_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--allow-partial-rollback",
            ),
            project_dir=project_dir,
        )
        assert blocked_result.returncode == 1
        for fragment in test_case.expected_stdout_fragments[:2]:
            assert fragment in blocked_result.stderr

        rollback_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-rollback",
            ),
            project_dir=project_dir,
        )

        assert rollback_result.returncode == test_case.expected_exit_code, rollback_result.stderr
        for fragment in test_case.expected_stdout_fragments[2:]:
            assert fragment in rollback_result.stdout
        logical_relation: str = quoted_relation_name(
            schema_name=f"{warehouse_schema}__dev",
            name="fact_orders",
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
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical", config=postgres_e2e_config
        )


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresVirtualSeedE2ETestCase(
            description="postgres virtual seeded incremental build uses copy",
            expected_rows=((1, 10), (2, 21), (3, 31)),
            expected_seed_strategy="copy",
        ),
        PostgresVirtualSeedE2ETestCase(
            description="postgres virtual append bounded seeded build uses bounded copy",
            expected_rows=((1, 10), (2, 21), (3, 31)),
            expected_seed_strategy="bounded_append_copy",
            incremental_strategy="append",
        ),
    ),
    ids=lambda case: case.description,
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
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[targets.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n\n'
                "[targets.dev.state.connection]\n"
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
                f"  incremental_strategy {test_case.incremental_strategy},\n"
                "  cursor ordered_at,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain day,\n"
                "  replay_on_change bounded-7d\n"
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
                f"  incremental_strategy {test_case.incremental_strategy},\n"
                "  cursor ordered_at,\n"
                "  cursor_type timestamp,\n"
                "  cursor_grain day,\n"
                "  replay_on_change bounded-7d\n"
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
        PostgresVirtualParityE2ETestCase(
            description="postgres virtual plan and partial build parity",
            expected_stdout_fragments=(
                "Plan ready (0 selected)",
                "status: finalized",
                "Query changed (1)",
                "stale root set: stg_orders",
                "cause: stg_orders (query changed)",
                "missing stale required upstream models: stg_orders",
                "Plan ready (2 selected)",
                '"virtual_environment_name": "dev"',
                "status: working",
                "remaining stale after selection",
                "Plan ready (0 selected)",
            ),
            expected_rows=((2,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_virtual_plan_and_partial_build_when_running_then_matches_duckdb_parity(
    test_case: PostgresVirtualParityE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_parity")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_plan_build_parity",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_virtual_plan_build_parity",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 1 AS id",
        )
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        build_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert build_result.returncode == test_case.expected_exit_code, build_result.stderr
        assert "name: dev" in build_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT id FROM "
                f"{
                    quoted_relation_name(
                        schema_name=f'{warehouse_schema}__dev',
                        name='fact_orders',
                    )
                }"
            ),
            config=postgres_e2e_config,
        ) == ((1,),)
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                "AND table_name = '_sqlbuild_fingerprints'"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)
        physical_rows_before: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                "AND table_name LIKE '%__v_%' ORDER BY table_name"
            ),
            config=postgres_e2e_config,
        )
        repeat_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert repeat_build.returncode == test_case.expected_exit_code, repeat_build.stderr
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT table_name FROM information_schema.tables "
                    f"WHERE table_schema = '{warehouse_schema}__sqb_physical' "
                    "AND table_name LIKE '%__v_%' ORDER BY table_name"
                ),
                config=postgres_e2e_config,
            )
            == physical_rows_before
        )
        matching_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "plan"),
            project_dir=project_dir,
        )
        assert matching_plan.returncode == test_case.expected_exit_code, matching_plan.stderr
        for fragment in test_case.expected_stdout_fragments[:2]:
            assert fragment in matching_plan.stdout

        (project_dir / "models" / "stg_orders.sql").write_text("MODEL ();\n\nSELECT 2 AS id\n")
        stale_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "plan"),
            project_dir=project_dir,
        )
        assert stale_plan.returncode == test_case.expected_exit_code, stale_plan.stderr
        for fragment in test_case.expected_stdout_fragments[2:5]:
            assert fragment in stale_plan.stdout
        assert "dim_customers" not in stale_plan.stdout
        selected_block: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "plan", "--select", "fact_orders"),
            project_dir=project_dir,
        )
        assert selected_block.returncode == 1
        assert test_case.expected_stdout_fragments[5] in selected_block.stderr
        include_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "plan",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            project_dir=project_dir,
        )
        assert include_plan.returncode == test_case.expected_exit_code, include_plan.stderr
        assert test_case.expected_stdout_fragments[6] in include_plan.stdout
        json_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=("plan", "--json"),
            project_dir=project_dir,
        )
        assert json_plan.returncode == test_case.expected_exit_code, json_plan.stderr
        parsed: dict[str, object] = json.loads(json_plan.stdout)
        assert "metadata" in parsed
        assert test_case.expected_stdout_fragments[7] in json_plan.stdout

        partial_build: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "build",
                "--virtual-env",
                "pr",
                "--select",
                "+fact_orders",
            ),
            project_dir=project_dir,
        )
        assert partial_build.returncode == test_case.expected_exit_code, partial_build.stderr
        for fragment in test_case.expected_stdout_fragments[8:10]:
            assert fragment in partial_build.stdout
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT id FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{warehouse_schema}__pr',
                            name='fact_orders',
                        )
                    }"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
        final_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"),
            project_dir=project_dir,
        )
        assert final_build.returncode == test_case.expected_exit_code, final_build.stderr
        final_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "plan", "--virtual-env", "pr"),
            project_dir=project_dir,
        )
        assert final_plan.returncode == test_case.expected_exit_code, final_plan.stderr
        assert test_case.expected_stdout_fragments[10] in final_plan.stdout
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualParityE2ETestCase(
            description="postgres virtual config and function change plan parity",
            expected_stdout_fragments=(
                "Config changed (1)",
                "config diff:",
                '"materialized": "view"',
                '"materialized": "table"',
                "Changed functions (1)",
                "is_large_order",
                "query diff:",
                "cause: is_large_order (function changed)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_config_and_function_changes_when_planning_then_reasons_match_parity(
    test_case: PostgresVirtualParityE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    config_state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    config_warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_config")
    function_state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    function_warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_function")
    config_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_config_plan",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_project_toml(
                project_name="postgres_virtual_config_plan",
                config=postgres_e2e_config,
                state_schema=config_state_schema,
                warehouse_schema=config_warehouse_schema,
            ),
            "models/stg_orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        },
    )
    function_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_function_plan",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_virtual_function_plan",
            config=postgres_e2e_config,
            state_schema=function_state_schema,
            warehouse_schema=function_warehouse_schema,
            stg_orders_sql="SELECT 7 AS id",
        )
        | {
            "models/fact_orders.sql": (
                "MODEL ();\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large FROM __ref("stg_orders")\n'
            ),
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "SELECT amount > 9\n"
            ),
        },
    )

    try:
        assert (
            run_sqb(
                command=("--no-color", "state", "init"), project_dir=config_project_dir
            ).returncode
            == 0
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=config_project_dir).returncode == 0
        )
        (config_project_dir / "models" / "stg_orders.sql").write_text(
            "MODEL (materialized table);\n\nSELECT 1 AS id\n"
        )
        config_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "plan"),
            project_dir=config_project_dir,
        )
        assert config_plan.returncode == test_case.expected_exit_code, config_plan.stderr
        for fragment in test_case.expected_stdout_fragments[:3]:
            assert fragment in config_plan.stdout
        assert "Query changed" not in config_plan.stdout

        assert (
            run_sqb(
                command=("--no-color", "state", "init"), project_dir=function_project_dir
            ).returncode
            == 0
        )
        assert (
            run_sqb(command=("--no-color", "build"), project_dir=function_project_dir).returncode
            == 0
        )
        (function_project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
            "FUNCTION ("
            "arguments (amount INTEGER), returns BOOLEAN, replay_on_change full"
            ");\n\n"
            "SELECT amount > 5\n"
        )
        function_plan: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "plan"),
            project_dir=function_project_dir,
        )
        assert function_plan.returncode == test_case.expected_exit_code, function_plan.stderr
        for fragment in test_case.expected_stdout_fragments[4:]:
            assert fragment in function_plan.stdout
    finally:
        cleanup_postgres_state_schemas(schema_name=config_state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=config_warehouse_schema, config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{config_warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{config_warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=function_state_schema, config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=function_warehouse_schema, config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{function_warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{function_warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualParityE2ETestCase(
            description="postgres virtual diff and promotion parity",
            expected_stdout_fragments=(
                "whole-VDE virtual diff requires finalized VDEs",
                "Virtual diff",
                "Virtual promotion complete",
                "pr_full -> dev",
                "target status          finalized",
                "promoted models        4",
                "promotion would leave target virtual environment working",
                "whole-VDE promotion requires a finalized source virtual environment",
                "virtual environment 'dev' is locked",
                "target status          working",
                "promoted models        2",
                "remaining stale set: orders_rollup",
                "fact_orders",
            ),
            expected_rows=((3,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_virtual_diff_and_promotion_when_running_then_matches_duckdb_parity(
    test_case: PostgresVirtualParityE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_promote")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_promote_parity",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_virtual_promote_parity",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 1 AS id",
        )
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "models" / "stg_orders.sql").write_text("MODEL ();\n\nSELECT 2 AS id\n")
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr_full"),
                project_dir=project_dir,
            ).returncode
            == 0
        )
        whole_promote: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "promote", "--from", "pr_full", "--to", "dev"),
            project_dir=project_dir,
        )
        assert whole_promote.returncode == test_case.expected_exit_code, whole_promote.stderr
        for fragment in test_case.expected_stdout_fragments[2:6]:
            assert fragment in whole_promote.stdout

        (project_dir / "models" / "stg_orders.sql").write_text("MODEL ();\n\nSELECT 3 AS id\n")
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr", "--select", "+fact_orders"),
                project_dir=project_dir,
            ).returncode
            == 0
        )
        blocked_diff: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "diff", "dev:pr", "--schema-only"),
            project_dir=project_dir,
        )
        assert blocked_diff.returncode == 1
        assert test_case.expected_stdout_fragments[0] in blocked_diff.stderr
        allowed_diff: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "diff", "dev:pr", "--schema-only", "--allow-partial-diff"),
            project_dir=project_dir,
        )
        assert allowed_diff.returncode == test_case.expected_exit_code, allowed_diff.stderr
        assert test_case.expected_stdout_fragments[1] in allowed_diff.stdout
        whole_working_source: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            project_dir=project_dir,
        )
        assert whole_working_source.returncode == 1
        assert test_case.expected_stdout_fragments[7] in (
            whole_working_source.stdout + whole_working_source.stderr
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
        locked_promote: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            project_dir=project_dir,
        )
        assert locked_promote.returncode == 1
        assert test_case.expected_stdout_fragments[8] in (
            locked_promote.stdout + locked_promote.stderr
        )
        execute_postgres_sql(
            sql=(
                "DELETE FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='locks')} "
                "WHERE lock_key = 'virtual_env:dev'"
            ),
            config=postgres_e2e_config,
        )
        blocked_promote: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            project_dir=project_dir,
        )
        assert blocked_promote.returncode == 1
        assert test_case.expected_stdout_fragments[6] in (
            blocked_promote.stdout + blocked_promote.stderr
        )
        partial_promote: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            project_dir=project_dir,
        )
        assert partial_promote.returncode == test_case.expected_exit_code, partial_promote.stderr
        for fragment in test_case.expected_stdout_fragments[9:12]:
            assert fragment in partial_promote.stdout
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT id FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{warehouse_schema}__dev',
                            name='fact_orders',
                        )
                    }"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT physical_relations.schema_name, physical_relations.relation_name FROM "
                f"{
                    quoted_relation_name(
                        schema_name=state_schema,
                        name='virtual_environment_node_refs',
                    )
                } "
                "AS refs JOIN "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "AS physical_relations ON physical_relations.artifact_type = 'model' "
                "AND physical_relations.artifact_name = refs.node_name "
                "AND physical_relations.version_hash = refs.version_hash "
                "WHERE refs.virtual_environment_name = 'pr' "
                "AND refs.node_type = 'model' AND refs.node_name = 'fact_orders'"
            ),
            config=postgres_e2e_config,
        )[0]
        execute_postgres_sql(
            sql=(
                "DROP TABLE "
                f"{
                    quoted_relation_name(
                        schema_name=str(physical_schema_name),
                        name=str(physical_relation_name),
                    )
                } "
                "CASCADE"
            ),
            config=postgres_e2e_config,
        )
        missing_physical_promote: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            project_dir=project_dir,
        )
        assert missing_physical_promote.returncode == 1
        assert test_case.expected_stdout_fragments[12] in (
            missing_physical_promote.stdout + missing_physical_promote.stderr
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr_full", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualParityE2ETestCase(
            description="postgres virtual promotion publishes function definitions",
            expected_stdout_fragments=(
                "Virtual promotion complete",
                "pr -> dev",
                "target status          finalized",
            ),
            expected_rows=((True,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_function_change_when_promoting_then_publishes_function_definition(
    test_case: PostgresVirtualParityE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    state_schema: str = build_unique_schema_name(prefix="sqb_state_e2e")
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_virtual_func_promote")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_function_promote",
        repo_files=build_postgres_virtual_plan_repo_files(
            project_name="postgres_virtual_function_promote",
            config=postgres_e2e_config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
            stg_orders_sql="SELECT 7 AS id",
        )
        | {
            "models/fact_orders.sql": (
                "MODEL (materialized view);\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large FROM __ref("stg_orders")\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "SELECT amount > 9\n"
            ),
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        assert fetch_postgres_rows(
            sql=(
                "SELECT "
                f"{
                    quoted_relation_name(
                        schema_name=f'{warehouse_schema}__dev',
                        name='is_large_order',
                    )
                }"
                "(7)"
            ),
            config=postgres_e2e_config,
        ) == ((False,),)
        function_refs_relation: str = quoted_relation_name(
            schema_name=state_schema,
            name="virtual_environment_node_refs",
        )
        initial_dev_function_hash: str = str(
            fetch_postgres_rows(
                sql=(
                    f"SELECT version_hash FROM {function_refs_relation} "
                    "WHERE virtual_environment_name = 'dev' "
                    "AND node_type = 'udf' AND node_name = 'is_large_order'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )

        (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
            "FUNCTION ("
            "arguments (amount INTEGER), returns BOOLEAN, replay_on_change full"
            ");\n\n"
            "SELECT amount > 5\n",
            encoding="utf-8",
        )
        assert (
            run_sqb(
                command=("--no-color", "build", "--virtual-env", "pr"),
                project_dir=project_dir,
            ).returncode
            == 0
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT is_large FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{warehouse_schema}__pr',
                            name='fact_orders',
                        )
                    }"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
        assert fetch_postgres_rows(
            sql=(
                "SELECT is_large FROM "
                f"{
                    quoted_relation_name(
                        schema_name=f'{warehouse_schema}__dev',
                        name='fact_orders',
                    )
                }"
            ),
            config=postgres_e2e_config,
        ) == ((False,),)
        pr_function_hash: str = str(
            fetch_postgres_rows(
                sql=(
                    f"SELECT version_hash FROM {function_refs_relation} "
                    "WHERE virtual_environment_name = 'pr' "
                    "AND node_type = 'udf' AND node_name = 'is_large_order'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        assert pr_function_hash != initial_dev_function_hash

        promote_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            project_dir=project_dir,
        )
        assert promote_result.returncode == test_case.expected_exit_code, promote_result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in promote_result.stdout
        assert fetch_postgres_rows(
            sql=(
                f"SELECT node_name, version_hash FROM {function_refs_relation} "
                "WHERE virtual_environment_name = 'dev' AND node_type = 'udf'"
            ),
            config=postgres_e2e_config,
        ) == (("is_large_order", pr_function_hash),)
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT is_large FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{warehouse_schema}__dev',
                            name='fact_orders',
                        )
                    }"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{warehouse_schema}__dev',
                            name='is_large_order',
                        )
                    }"
                    "(7)"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
    finally:
        cleanup_postgres_state_schemas(schema_name=state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__dev", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__pr", config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualParityE2ETestCase(
            description="postgres standard mode promotion guard",
            expected_stdout_fragments=("promote requires virtual_environments = true",),
            expected_exit_code=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_direct_mode_project_when_promoting_then_fails_with_mode_error(
    test_case: PostgresVirtualParityE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    warehouse_schema: str = build_unique_schema_name(prefix="sqb_direct_promote")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_direct_promote_guard",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "postgres_direct_promote_guard"\n'
                'adapter = "postgres"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n'
            ),
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
        assert test_case.expected_stdout_fragments[0] in result.stderr
    finally:
        cleanup_postgres_state_schemas(schema_name=warehouse_schema, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresVirtualParityE2ETestCase(
            description="postgres virtual clone parity",
            expected_stdout_fragments=(
                "mode                    workspace fingerprints",
                "origin state            not used",
                "hydrated             3",
                "mode                    destination VDE refs",
                "destination VDE         dev",
                "hydrated             1",
                "already present      2",
                "missing in origin    0",
                "missing: stg_orders",
                "is locked",
                "skipped locked       1",
                "skipped locked: stg_orders",
            ),
            expected_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_virtual_clone_when_running_then_matches_duckdb_parity(
    test_case: PostgresVirtualParityE2ETestCase,
    tmp_path: Path,
    postgres_e2e_config: dict[str, object],
) -> None:
    prod_state_schema: str = build_unique_schema_name(prefix="sqb_prod_state_e2e")
    dev_state_schema: str = build_unique_schema_name(prefix="sqb_dev_state_e2e")
    prod_warehouse_schema: str = build_unique_schema_name(prefix="sqb_clone_prod")
    dev_warehouse_schema: str = build_unique_schema_name(prefix="sqb_clone_dev")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_virtual_clone_parity",
        repo_files={
            "sqlbuild_project.toml": build_postgres_virtual_clone_project_toml(
                project_name="postgres_virtual_clone_parity",
                config=postgres_e2e_config,
                prod_state_schema=prod_state_schema,
                dev_state_schema=dev_state_schema,
                prod_warehouse_schema=prod_warehouse_schema,
                dev_warehouse_schema=dev_warehouse_schema,
            ),
            "sqlbuild_local.toml": 'target = "prod"\n',
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 7 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
            "models/dim_customers.sql": "MODEL ();\n\nSELECT 1 AS customer_id\n",
        },
    )

    try:
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n')
        assert (
            run_sqb(command=("--no-color", "state", "init"), project_dir=project_dir).returncode
            == 0
        )
        clone_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "clone", "--from", "prod", "--to", "dev"),
            project_dir=project_dir,
        )
        assert clone_result.returncode == test_case.expected_exit_code, clone_result.stderr
        for fragment in test_case.expected_stdout_fragments[:3]:
            assert fragment in clone_result.stdout
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM information_schema.tables "
                f"WHERE table_schema = '{dev_warehouse_schema}__sqb_physical' "
                "AND table_name LIKE '%__v_%'"
            ),
            config=postgres_e2e_config,
        ) == ((3,),)
        stg_hash: str = str(
            fetch_postgres_rows(
                sql=(
                    "SELECT version_hash FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=prod_state_schema,
                            name='virtual_environment_node_refs',
                        )
                    } "
                    "WHERE virtual_environment_name = 'prod' "
                    "AND node_type = 'model' AND node_name = 'stg_orders'"
                ),
                config=postgres_e2e_config,
            )[0][0]
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT id FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{dev_warehouse_schema}__sqb_physical',
                            name=f'stg_orders__v_{stg_hash[:8]}',
                        )
                    }"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )
        assert fetch_postgres_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{
                    quoted_relation_name(
                        schema_name=dev_state_schema,
                        name='virtual_environment_node_refs',
                    )
                }"
            ),
            config=postgres_e2e_config,
        ) == ((0,),)

        assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
        dev_ref_rows_before: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                "SELECT node_name, version_hash FROM "
                f"{
                    quoted_relation_name(
                        schema_name=dev_state_schema,
                        name='virtual_environment_node_refs',
                    )
                } "
                "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
                "ORDER BY node_name"
            ),
            config=postgres_e2e_config,
        )
        execute_postgres_sql(
            sql=(
                "DROP TABLE "
                f"{
                    quoted_relation_name(
                        schema_name=f'{dev_warehouse_schema}__sqb_physical',
                        name=f'stg_orders__v_{stg_hash[:8]}',
                    )
                } "
                "CASCADE"
            ),
            config=postgres_e2e_config,
        )
        target_ref_clone: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--virtual-env",
                "dev",
            ),
            project_dir=project_dir,
        )
        assert target_ref_clone.returncode == test_case.expected_exit_code, target_ref_clone.stderr
        for fragment in test_case.expected_stdout_fragments[3:8]:
            assert fragment in target_ref_clone.stdout
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT node_name, version_hash FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=dev_state_schema,
                            name='virtual_environment_node_refs',
                        )
                    } "
                    "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
                    "ORDER BY node_name"
                ),
                config=postgres_e2e_config,
            )
            == dev_ref_rows_before
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT id FROM "
                    f"{
                        quoted_relation_name(
                            schema_name=f'{dev_warehouse_schema}__sqb_physical',
                            name=f'stg_orders__v_{stg_hash[:8]}',
                        )
                    }"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_rows
        )

        execute_postgres_sql(
            sql=(
                "DROP TABLE "
                f"{
                    quoted_relation_name(
                        schema_name=f'{prod_warehouse_schema}__sqb_physical',
                        name=f'stg_orders__v_{stg_hash[:8]}',
                    )
                }"
                " CASCADE"
            ),
            config=postgres_e2e_config,
        )
        missing_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "stg_orders",
            ),
            project_dir=project_dir,
        )
        assert missing_result.returncode == 1
        assert test_case.expected_stdout_fragments[8] in missing_result.stdout
        execute_postgres_sql(
            sql=(
                "CREATE TABLE "
                f"{
                    quoted_relation_name(
                        schema_name=f'{prod_warehouse_schema}__sqb_physical',
                        name=f'stg_orders__v_{stg_hash[:8]}',
                    )
                } "
                "AS SELECT 7 AS id"
            ),
            config=postgres_e2e_config,
        )
        execute_postgres_sql(
            sql=(
                "INSERT INTO "
                f"{quoted_relation_name(schema_name=dev_state_schema, name='locks')} "
                "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
                f"('model_version:stg_orders:{stg_hash}', 'test', TIMESTAMP '2999-01-01', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            config=postgres_e2e_config,
        )
        locked_result: subprocess.CompletedProcess[str] = run_sqb(
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "stg_orders",
            ),
            project_dir=project_dir,
        )
        assert locked_result.returncode == 1
        for fragment in test_case.expected_stdout_fragments[9:10]:
            assert fragment in locked_result.stderr
        skip_locked_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "clone", "--from", "prod", "--to", "dev", "--skip-locked"),
            project_dir=project_dir,
        )
        assert skip_locked_result.returncode == test_case.expected_exit_code, (
            skip_locked_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments[10:]:
            assert fragment in skip_locked_result.stdout
    finally:
        cleanup_postgres_state_schemas(schema_name=prod_state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(schema_name=dev_state_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=prod_warehouse_schema, config=postgres_e2e_config
        )
        cleanup_postgres_state_schemas(schema_name=dev_warehouse_schema, config=postgres_e2e_config)
        cleanup_postgres_state_schemas(
            schema_name=f"{prod_warehouse_schema}__prod",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{dev_warehouse_schema}__dev",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{prod_warehouse_schema}__sqb_physical",
            config=postgres_e2e_config,
        )
        cleanup_postgres_state_schemas(
            schema_name=f"{dev_warehouse_schema}__sqb_physical",
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
    ids=lambda case: case.description,
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
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[targets.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n\n'
                "[targets.dev.state.connection]\n"
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
    ids=lambda case: case.description,
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
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n"
                "[connection]\n"
                f'host = "{postgres_e2e_config["host"]}"\n'
                f"port = {postgres_e2e_config['port']}\n"
                f'dbname = "{postgres_e2e_config["dbname"]}"\n'
                f'user = "{postgres_e2e_config["user"]}"\n'
                f'password = "{postgres_e2e_config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{warehouse_schema}"\n\n'
                "[targets.dev.state]\n"
                'backend = "postgres"\n'
                f'schema = "{state_schema}"\n\n'
                "[targets.dev.state.connection]\n"
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
                "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
                "ORDER BY updated_at DESC LIMIT 1"
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
    ids=lambda case: case.description,
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
                "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
                "ORDER BY updated_at DESC LIMIT 1"
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
            name="virtual_environment_node_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' "
                "AND node_type = 'model' AND node_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE artifact_type = 'model' AND artifact_name = 'customers' "
                "ORDER BY updated_at DESC LIMIT 1"
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
                    "WHERE virtual_environment_name = 'dev' "
                    "AND node_type = 'model' AND node_name = 'orders'"
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
    ids=lambda case: case.description,
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
            name="virtual_environment_node_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' "
                "AND node_type = 'model' AND node_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
                "ORDER BY updated_at DESC LIMIT 1"
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
                    "WHERE virtual_environment_name = 'dev' "
                    "AND node_type = 'model' AND node_name = 'orders'"
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
            name="virtual_environment_node_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' "
                "AND node_type = 'model' AND node_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
                "ORDER BY updated_at DESC LIMIT 1"
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
                    "WHERE virtual_environment_name = 'dev' "
                    "AND node_type = 'model' AND node_name = 'orders'"
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
            name="virtual_environment_node_refs",
        )
        original_refs: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
            sql=(
                f"SELECT version_hash FROM {refs_relation} "
                "WHERE virtual_environment_name = 'dev' "
                "AND node_type = 'model' AND node_name = 'orders'"
            ),
            config=postgres_e2e_config,
        )
        physical_schema_name, physical_relation_name = fetch_postgres_rows(
            sql=(
                "SELECT schema_name, relation_name FROM "
                f"{quoted_relation_name(schema_name=state_schema, name='physical_relations')} "
                "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
                "ORDER BY updated_at DESC LIMIT 1"
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
                    "WHERE virtual_environment_name = 'dev' "
                    "AND node_type = 'model' AND node_name = 'orders'"
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
    (
        PostgresStateLifecycleErrorE2ETestCase(
            description="reset blocks when allow reset is false",
            allow_reset=False,
            command=("--no-color", "state", "reset", "--auto-approve"),
            expected_exit_code=1,
            expected_error_fragment=("set `allow_reset = true` under `[targets.<name>.state]`"),
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
    ),
    ids=lambda case: case.description,
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
    (
        PostgresStateSchemaCorruptionE2ETestCase(
            description="postgres migrate blocks cleanly when required state table is missing",
            mutation_sql_template="DROP TABLE {virtual_environment_node_refs}",
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
    ),
    ids=lambda case: case.description,
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
                virtual_environment_node_refs=quoted_relation_name(
                    schema_name=state_schema,
                    name="virtual_environment_node_refs",
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
