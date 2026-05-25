from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.versioned.state.models import StateSchemaValidationResult
from sqlbuild.versioned.state.types import StateMigrationAction
from tests.integration.src.sqlbuild.versioned.state.classes._test_types import (
    DuckDbStateBackendErrorTestCase,
    DuckDbStateBackendEventTestCase,
    DuckDbStateBackendIdempotencyTestCase,
    DuckDbStateBackendLifecycleTestCase,
    DuckDbStateBackendRollbackTestCase,
    DuckDbStateBackendValidationTestCase,
)
from tests.integration.src.sqlbuild.versioned.state.classes.helpers import (
    fetch_all,
    open_duckdb_state_backend,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendLifecycleTestCase(
            description="initializes backs up rolls back and resets state tables",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            expected_schema_version=1,
            expected_backup_prefix="sqlbuild_state__backup_",
        )
    ],
    ids=["initializes backs up rolls back and resets state tables"],
)
def test_given_duckdb_state_backend_when_running_lifecycle_then_state_tables_are_managed(
    test_case: DuckDbStateBackendLifecycleTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        version_rows: list[tuple[object, ...]] = fetch_all(
            connection,
            f"SELECT schema_version, sqlbuild_version FROM {test_case.schema}.state_versions",
        )
        assert version_rows == [(test_case.expected_schema_version, test_case.sqlbuild_version)]
        assert backend.validate_schema(connection, schema=test_case.schema).valid

        backup_id: str = backend.create_backup(connection, schema=test_case.schema)
        assert backup_id
        backup_schemas: list[tuple[object, ...]] = fetch_all(
            connection,
            "SELECT schema_name FROM information_schema.schemata "
            f"WHERE schema_name = '{test_case.expected_backup_prefix}{backup_id}'",
        )
        assert backup_schemas == [(f"{test_case.expected_backup_prefix}{backup_id}",)]

        connection.execute(f"DELETE FROM {test_case.schema}.state_versions")
        assert fetch_all(connection, f"SELECT * FROM {test_case.schema}.state_versions") == []

        rolled_back_backup_id: str = backend.rollback(connection, schema=test_case.schema)
        assert rolled_back_backup_id == backup_id
        assert fetch_all(
            connection,
            f"SELECT schema_version, sqlbuild_version FROM {test_case.schema}.state_versions",
        ) == [(test_case.expected_schema_version, test_case.sqlbuild_version)]

        backend.reset(connection, schema=test_case.schema)
        validation_after_reset: StateSchemaValidationResult = backend.validate_schema(
            connection,
            schema=test_case.schema,
        )
        assert not validation_after_reset.valid
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendValidationTestCase(
            description="reports invalid manually-created state schema",
            schema="broken_state",
            expected_issue_count=3,
        )
    ],
    ids=["reports invalid manually-created state schema"],
)
def test_given_broken_duckdb_state_tables_when_validating_then_reports_schema_issues(
    test_case: DuckDbStateBackendValidationTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        connection.execute(f"CREATE SCHEMA {test_case.schema}")
        connection.execute(
            f"CREATE TABLE {test_case.schema}.state_versions ("
            "schema_version VARCHAR, updated_at TIMESTAMP)"
        )

        result: StateSchemaValidationResult = backend.validate_schema(
            connection,
            schema=test_case.schema,
        )

        assert len(result.issues) == test_case.expected_issue_count
        assert not result.valid
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendRollbackTestCase(
            description="rolls back to explicitly selected backup",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.before",
            expected_restored_sqlbuild_version="0.0.before",
        )
    ],
    ids=["rolls back to explicitly selected backup"],
)
def test_given_duckdb_state_backups_when_rolling_back_explicit_id_then_restores_backup(
    test_case: DuckDbStateBackendRollbackTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        first_backup_id: str = backend.create_backup(connection, schema=test_case.schema)
        backend.initialize(connection, schema=test_case.schema, sqlbuild_version="0.0.after")
        backend.create_backup(connection, schema=test_case.schema)

        backend.rollback(
            connection,
            schema=test_case.schema,
            backup_id=first_backup_id,
        )

        assert fetch_all(
            connection,
            f"SELECT sqlbuild_version FROM {test_case.schema}.state_versions",
        ) == [(test_case.expected_restored_sqlbuild_version,)]
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendErrorTestCase(
            description="blocks rollback when no backup exists",
            schema="sqlbuild_state",
            expected_error_type=Exception,
            expected_message_fragment="No state backup is available",
        )
    ],
    ids=["blocks rollback when no backup exists"],
)
def test_given_duckdb_state_without_backup_when_rolling_back_then_blocks_cleanly(
    test_case: DuckDbStateBackendErrorTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(connection, schema=test_case.schema, sqlbuild_version="0.0.test")
        with pytest.raises(test_case.expected_error_type) as exc_info:
            backend.rollback(connection, schema=test_case.schema)

        assert test_case.expected_message_fragment in str(exc_info.value)
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendErrorTestCase(
            description="blocks backup when state schema is invalid",
            schema="broken_state",
            expected_error_type=Exception,
            expected_message_fragment="Cannot backup invalid state schema",
        )
    ],
    ids=["blocks backup when state schema is invalid"],
)
def test_given_invalid_duckdb_state_schema_when_creating_backup_then_blocks_cleanly(
    test_case: DuckDbStateBackendErrorTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        connection.execute(f"CREATE SCHEMA {test_case.schema}")
        connection.execute(
            f"CREATE TABLE {test_case.schema}.state_versions (schema_version INTEGER)"
        )
        with pytest.raises(test_case.expected_error_type) as exc_info:
            backend.create_backup(connection, schema=test_case.schema)

        assert test_case.expected_message_fragment in str(exc_info.value)
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendEventTestCase(
            description="records init backup and rollback events with backed up event contents",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
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
    ids=["records init backup and rollback events with backed up event contents"],
)
def test_given_duckdb_state_lifecycle_when_events_are_recorded_then_backup_contains_event_table(
    test_case: DuckDbStateBackendEventTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backup_id: str = backend.create_backup(connection, schema=test_case.schema)
        backup_schema: str = f"{test_case.schema}__backup_{backup_id}"

        assert (
            tuple(
                row[0]
                for row in fetch_all(
                    connection,
                    "SELECT action FROM "
                    f"{test_case.schema}.state_migration_events ORDER BY created_at",
                )
            )
            == test_case.expected_actions_after_backup
        )
        assert (
            tuple(
                row[0]
                for row in fetch_all(
                    connection,
                    "SELECT action FROM "
                    f"{backup_schema}.state_migration_events ORDER BY created_at",
                )
            )
            == test_case.expected_backup_actions
        )

        connection.execute(f"DELETE FROM {test_case.schema}.state_versions")
        backend.rollback(connection, schema=test_case.schema, backup_id=backup_id)

        assert (
            tuple(
                row[0]
                for row in fetch_all(
                    connection,
                    "SELECT action FROM "
                    f"{test_case.schema}.state_migration_events ORDER BY created_at",
                )
            )
            == test_case.expected_actions_after_rollback
        )
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendIdempotencyTestCase(
            description="initialize can run sequentially without duplicate state version rows",
            schema="sqlbuild_state",
            first_sqlbuild_version="0.0.first",
            second_sqlbuild_version="0.0.second",
            expected_schema_version_rows=1,
            expected_latest_sqlbuild_version="0.0.second",
        )
    ],
    ids=["initialize can run sequentially without duplicate state version rows"],
)
def test_given_duckdb_state_backend_when_initializing_twice_then_current_version_row_is_idempotent(
    test_case: DuckDbStateBackendIdempotencyTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.first_sqlbuild_version,
        )
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.second_sqlbuild_version,
        )

        assert fetch_all(
            connection,
            f"SELECT COUNT(*), MAX(sqlbuild_version) FROM {test_case.schema}.state_versions",
        ) == [
            (
                test_case.expected_schema_version_rows,
                test_case.expected_latest_sqlbuild_version,
            )
        ]
    finally:
        backend.close(connection)
