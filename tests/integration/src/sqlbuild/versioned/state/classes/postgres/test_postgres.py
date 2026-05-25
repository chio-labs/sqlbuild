from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.versioned.state.classes.postgres import PostgresStateBackend
from sqlbuild.versioned.state.models import StateSchemaValidationResult
from sqlbuild.versioned.state.types import StateMigrationAction
from tests.integration.src.sqlbuild.versioned.state.classes.postgres._test_types import (
    PostgresStateBackendErrorTestCase,
    PostgresStateBackendExplicitRollbackTestCase,
    PostgresStateBackendLifecycleTestCase,
    PostgresStateBackendValidationTestCase,
)
from tests.integration.src.sqlbuild.versioned.state.classes.postgres.helpers import (
    fetch_all,
    qualified_name,
    quote_identifier,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendLifecycleTestCase(
            description="initializes backs up rolls back and resets state tables",
            sqlbuild_version="0.0.test",
            expected_schema_version=1,
            expected_actions_after_backup=(
                StateMigrationAction.INIT.value,
                StateMigrationAction.BACKUP.value,
            ),
            expected_actions_after_rollback=(
                StateMigrationAction.INIT.value,
                StateMigrationAction.ROLLBACK.value,
            ),
            expected_backup_actions=(StateMigrationAction.INIT.value,),
        )
    ],
    ids=["initializes backs up rolls back and resets state tables"],
)
def test_given_postgres_state_backend_when_running_lifecycle_then_state_tables_are_managed(
    test_case: PostgresStateBackendLifecycleTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    assert fetch_all(
        postgres_state_connection,
        "SELECT schema_version FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_versions')}",
    ) == [(test_case.expected_schema_version,)]
    assert postgres_state_backend.validate_schema(
        postgres_state_connection,
        schema=postgres_state_schema,
    ).valid

    backup_id: str = postgres_state_backend.create_backup(
        postgres_state_connection,
        schema=postgres_state_schema,
    )
    backup_schema: str = f"{postgres_state_schema}__backup_{backup_id}"
    assert fetch_all(
        postgres_state_connection,
        "SELECT action FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_migration_events')} "
        "ORDER BY created_at",
    ) == [(action,) for action in test_case.expected_actions_after_backup]
    assert fetch_all(
        postgres_state_connection,
        "SELECT action FROM "
        f"{qualified_name(schema=backup_schema, table='state_migration_events')} "
        "ORDER BY created_at",
    ) == [(action,) for action in test_case.expected_backup_actions]

    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {qualified_name(schema=postgres_state_schema, table='state_versions')}"
        )
    assert (
        fetch_all(
            postgres_state_connection,
            f"SELECT * FROM {qualified_name(schema=postgres_state_schema, table='state_versions')}",
        )
        == []
    )

    rolled_back_backup_id: str = postgres_state_backend.rollback(
        postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert rolled_back_backup_id == backup_id
    assert fetch_all(
        postgres_state_connection,
        "SELECT action FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_migration_events')} "
        "ORDER BY created_at",
    ) == [(action,) for action in test_case.expected_actions_after_rollback]

    postgres_state_backend.reset(postgres_state_connection, schema=postgres_state_schema)
    validation_after_reset: StateSchemaValidationResult = postgres_state_backend.validate_schema(
        postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert not validation_after_reset.valid


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendValidationTestCase(
            description="reports invalid manually-created state schema",
            expected_issue_count=3,
        )
    ],
    ids=["reports invalid manually-created state schema"],
)
def test_given_broken_postgres_state_tables_when_validating_then_reports_schema_issues(
    test_case: PostgresStateBackendValidationTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {quote_identifier(postgres_state_schema)}")
        cursor.execute(
            f"CREATE TABLE {qualified_name(schema=postgres_state_schema, table='state_versions')} ("
            "schema_version TEXT, updated_at TIMESTAMP)"
        )

    result: StateSchemaValidationResult = postgres_state_backend.validate_schema(
        postgres_state_connection,
        schema=postgres_state_schema,
    )

    assert len(result.issues) == test_case.expected_issue_count
    assert not result.valid


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendErrorTestCase(
            description="blocks rollback when no backup exists",
            expected_error_type=Exception,
            expected_message_fragment="No state backup is available",
        )
    ],
    ids=["blocks rollback when no backup exists"],
)
def test_given_postgres_state_without_backup_when_rolling_back_then_blocks_cleanly(
    test_case: PostgresStateBackendErrorTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="0.0.test",
    )

    with pytest.raises(test_case.expected_error_type) as exc_info:
        postgres_state_backend.rollback(postgres_state_connection, schema=postgres_state_schema)

    assert test_case.expected_message_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendErrorTestCase(
            description="blocks backup when state schema is invalid",
            expected_error_type=Exception,
            expected_message_fragment="Cannot backup invalid state schema",
        )
    ],
    ids=["blocks backup when state schema is invalid"],
)
def test_given_invalid_postgres_state_schema_when_creating_backup_then_blocks_cleanly(
    test_case: PostgresStateBackendErrorTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {quote_identifier(postgres_state_schema)}")
        cursor.execute(
            f"CREATE TABLE {qualified_name(schema=postgres_state_schema, table='state_versions')} "
            "(schema_version INTEGER)"
        )

    with pytest.raises(test_case.expected_error_type) as exc_info:
        postgres_state_backend.create_backup(
            postgres_state_connection, schema=postgres_state_schema
        )

    assert test_case.expected_message_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendExplicitRollbackTestCase(
            description="rolls back to explicitly selected backup",
            sqlbuild_version="0.0.test",
            expected_restored_schema_version=1,
        )
    ],
    ids=["rolls back to explicitly selected backup"],
)
def test_given_postgres_state_backups_when_rolling_back_explicit_id_then_restores_backup(
    test_case: PostgresStateBackendExplicitRollbackTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    first_backup_id: str = postgres_state_backend.create_backup(
        postgres_state_connection,
        schema=postgres_state_schema,
    )
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE "
            f"{qualified_name(schema=postgres_state_schema, table='state_versions')} "
            "SET schema_version = 2"
        )
    postgres_state_backend.create_backup(postgres_state_connection, schema=postgres_state_schema)
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {qualified_name(schema=postgres_state_schema, table='state_versions')}"
        )

    postgres_state_backend.rollback(
        postgres_state_connection,
        schema=postgres_state_schema,
        backup_id=first_backup_id,
    )

    assert fetch_all(
        postgres_state_connection,
        "SELECT schema_version FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_versions')}",
    ) == [(test_case.expected_restored_schema_version,)]
