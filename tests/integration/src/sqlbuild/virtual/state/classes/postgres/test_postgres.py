from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import psycopg
import pytest

from sqlbuild.virtual.state.classes.postgres import PostgresStateBackend
from sqlbuild.virtual.state.constants import STATE_TABLE_INDEXES, STATE_TABLES
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    StateLockRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    StateMigrationAction,
    StateSchemaValidationIssueKind,
    VirtualEnvironmentStatus,
)
from tests.integration.src.sqlbuild.virtual.state.classes.postgres._test_types import (
    PostgresStateBackendConcurrentLockTestCase,
    PostgresStateBackendCoreRecordsTestCase,
    PostgresStateBackendErrorTestCase,
    PostgresStateBackendExplicitRollbackTestCase,
    PostgresStateBackendIndexValidationTestCase,
    PostgresStateBackendLifecycleTestCase,
    PostgresStateBackendLockTestCase,
    PostgresStateBackendTableCreationTestCase,
    PostgresStateBackendTransactionRollbackTestCase,
    PostgresStateBackendValidationTestCase,
)
from tests.integration.src.sqlbuild.virtual.state.classes.postgres.helpers import (
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
            expected_issue_count=16,
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
            expected_index_names=tuple(
                sorted(
                    index_name for indexes in STATE_TABLE_INDEXES.values() for index_name in indexes
                )
            ),
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
    assert (
        tuple(
            row[0]
            for row in fetch_all(
                postgres_state_connection,
                "SELECT indexname FROM pg_indexes "
                f"WHERE schemaname = '{postgres_state_schema}' ORDER BY indexname",
            )
        )
        == test_case.expected_index_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendTableCreationTestCase(
            description="initializes all phase two state tables",
            sqlbuild_version="0.0.test",
            expected_table_names=tuple(sorted(STATE_TABLES)),
            expected_index_names=tuple(
                sorted(
                    index_name for indexes in STATE_TABLE_INDEXES.values() for index_name in indexes
                )
            ),
        )
    ],
    ids=["initializes all phase two state tables"],
)
def test_given_postgres_state_backend_when_initializing_then_creates_all_state_tables(
    test_case: PostgresStateBackendTableCreationTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )

    rows: list[tuple[Any, ...]] = fetch_all(
        postgres_state_connection,
        "SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{postgres_state_schema}' ORDER BY table_name",
    )
    index_rows: list[tuple[Any, ...]] = fetch_all(
        postgres_state_connection,
        "SELECT indexname FROM pg_indexes "
        f"WHERE schemaname = '{postgres_state_schema}' ORDER BY indexname",
    )

    assert tuple(row[0] for row in rows) == test_case.expected_table_names
    assert tuple(row[0] for row in index_rows) == test_case.expected_index_names


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendIndexValidationTestCase(
            description="reports missing unique state index",
            sqlbuild_version="0.0.test",
            dropped_index_name="idx_sqb_locks_identity",
            expected_issue_kind=StateSchemaValidationIssueKind.MISSING_INDEX.value,
        )
    ],
    ids=["reports missing unique state index"],
)
def test_given_postgres_state_backend_when_required_index_is_missing_then_validation_reports_it(
    test_case: PostgresStateBackendIndexValidationTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )

    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            "DROP INDEX "
            f"{qualified_name(schema=postgres_state_schema, table=test_case.dropped_index_name)}"
        )

    validation_result: StateSchemaValidationResult = postgres_state_backend.validate_schema(
        postgres_state_connection,
        schema=postgres_state_schema,
    )

    assert test_case.expected_issue_kind in tuple(
        issue.kind.value for issue in validation_result.issues
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendCoreRecordsTestCase(
            description="persists model physical relation and virtual environment refs",
            sqlbuild_version="0.0.test",
            expected_model_name="fact_orders",
            expected_version_hash="abc123",
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=["persists model physical relation and virtual environment refs"],
)
def test_given_postgres_state_backend_when_upserting_core_records_then_round_trips_state(
    test_case: PostgresStateBackendCoreRecordsTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    assert (
        postgres_state_backend.get_model_version(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        is None
    )
    assert (
        postgres_state_backend.get_physical_relation(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        is None
    )
    assert (
        postgres_state_backend.get_virtual_environment(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
        is None
    )
    model_record: ModelVersionRecord = ModelVersionRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        data_hash="data-hash",
        metadata_hash="metadata-hash",
        status=ModelVersionStatus.READY,
        fingerprint_query_sql_b64="U0VMRUNUIDEgQVMgaWQ=",
        fingerprint_metadata_json_b64="e30=",
        compiled_sql_b64="U0VMRUNUIDEgQVMgaWQ=",
    )
    postgres_state_backend.upsert_model_version(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=model_record,
    )
    relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=test_case.expected_relation_name,
        relation_type="table",
    )
    postgres_state_backend.upsert_physical_relation(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=relation_record,
    )
    replaced_relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=test_case.expected_replaced_relation_name,
        relation_type="table",
    )
    postgres_state_backend.upsert_physical_relation(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=replaced_relation_record,
    )
    ancestry_record: PhysicalRelationAncestryRecord = PhysicalRelationAncestryRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        parent_model_name=test_case.expected_model_name,
        parent_version_hash="parent123",
        seed_strategy="copy",
    )
    postgres_state_backend.upsert_physical_relation_ancestry(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=ancestry_record,
    )
    virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name=test_case.expected_virtual_environment_name,
        status=VirtualEnvironmentStatus.FINALIZED,
        baseline_virtual_environment_name=None,
    )
    postgres_state_backend.upsert_virtual_environment(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=virtual_environment_record,
    )
    postgres_state_backend.replace_virtual_environment_refs(
        postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.expected_virtual_environment_name,
        refs=(
            VirtualEnvironmentRefRecord(
                virtual_environment_name=test_case.expected_virtual_environment_name,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            ),
        ),
    )

    assert (
        postgres_state_backend.get_model_version(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == model_record
    )
    assert (
        postgres_state_backend.get_physical_relation(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == replaced_relation_record
    )
    assert (
        postgres_state_backend.get_physical_relation_ancestry(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == ancestry_record
    )
    assert (
        postgres_state_backend.get_virtual_environment(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
        == virtual_environment_record
    )
    refs: tuple[VirtualEnvironmentRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_refs(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
    )
    assert len(refs) == test_case.expected_ref_count
    assert refs[0].model_name == test_case.expected_model_name
    assert refs[0].version_hash == test_case.expected_version_hash
    postgres_state_backend.replace_virtual_environment_refs(
        postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.expected_virtual_environment_name,
        refs=(),
    )
    replaced_refs: tuple[VirtualEnvironmentRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_refs(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
    )
    assert len(replaced_refs) == test_case.expected_ref_count_after_replace


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendLockTestCase(
            description="acquires blocks releases and replaces expired locks",
            sqlbuild_version="0.0.test",
            lock_key="virtual_env:dev",
            first_owner="run-1",
            second_owner="run-2",
            expected_active_lock_count=1,
        )
    ],
    ids=["acquires blocks releases and replaces expired locks"],
)
def test_given_postgres_state_backend_when_managing_locks_then_enforces_active_owner(
    test_case: PostgresStateBackendLockTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    future_expiry: datetime = datetime.now() + timedelta(hours=1)
    expired_at: datetime = datetime.now() - timedelta(hours=1)

    assert postgres_state_backend.acquire_lock(
        postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.first_owner,
        expires_at=future_expiry,
    )
    assert not postgres_state_backend.acquire_lock(
        postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.second_owner,
        expires_at=future_expiry,
    )
    active_locks: tuple[StateLockRecord, ...] = postgres_state_backend.list_active_locks(
        postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert len(active_locks) == test_case.expected_active_lock_count
    assert active_locks[0].owner_id == test_case.first_owner
    assert not postgres_state_backend.release_lock(
        postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.second_owner,
    )
    assert postgres_state_backend.release_lock(
        postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.first_owner,
    )
    assert (
        postgres_state_backend.list_active_locks(
            postgres_state_connection,
            schema=postgres_state_schema,
        )
        == ()
    )
    assert postgres_state_backend.acquire_lock(
        postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.first_owner,
        expires_at=expired_at,
    )
    assert postgres_state_backend.acquire_lock(
        postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.second_owner,
        expires_at=future_expiry,
    )
    replacement_locks: tuple[StateLockRecord, ...] = postgres_state_backend.list_active_locks(
        postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert len(replacement_locks) == test_case.expected_active_lock_count
    assert replacement_locks[0].owner_id == test_case.second_owner


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendTransactionRollbackTestCase(
            description="rolls back VDE ref replacement when duplicate rows violate unique index",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            model_name="fact_orders",
            original_version_hash="abc123",
            duplicate_version_hash="def456",
            expected_ref_count=1,
        )
    ],
    ids=["rolls back VDE ref replacement when duplicate rows violate unique index"],
)
def test_given_postgres_state_backend_when_ref_replace_fails_then_transaction_rolls_back(
    test_case: PostgresStateBackendTransactionRollbackTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    postgres_state_backend.replace_virtual_environment_refs(
        postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        refs=(
            VirtualEnvironmentRefRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                model_name=test_case.model_name,
                version_hash=test_case.original_version_hash,
            ),
        ),
    )

    with pytest.raises(psycopg.errors.UniqueViolation):
        postgres_state_backend.replace_virtual_environment_refs(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
            refs=(
                VirtualEnvironmentRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    model_name=test_case.model_name,
                    version_hash=test_case.original_version_hash,
                ),
                VirtualEnvironmentRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    model_name=test_case.model_name,
                    version_hash=test_case.duplicate_version_hash,
                ),
            ),
        )

    refs: tuple[VirtualEnvironmentRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_refs(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
    )
    assert len(refs) == test_case.expected_ref_count
    assert refs[0].version_hash == test_case.original_version_hash


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendCoreRecordsTestCase(
            description="preserves created_at across current-state replacements",
            sqlbuild_version="0.0.test",
            expected_model_name="fact_orders",
            expected_version_hash="abc123",
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=["preserves created_at across current-state replacements"],
)
def test_given_postgres_state_backend_when_upserting_same_identity_then_created_at_is_preserved(
    test_case: PostgresStateBackendCoreRecordsTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    model_record: ModelVersionRecord = ModelVersionRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        data_hash="data-hash",
        metadata_hash="metadata-hash",
        status=ModelVersionStatus.READY,
    )
    postgres_state_backend.upsert_model_version(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=model_record,
    )
    original_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='model_versions')} "
        f"WHERE model_name = '{test_case.expected_model_name}' "
        f"AND version_hash = '{test_case.expected_version_hash}'",
    )[0][0]

    postgres_state_backend.upsert_model_version(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=model_record,
    )

    replaced_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='model_versions')} "
        f"WHERE model_name = '{test_case.expected_model_name}' "
        f"AND version_hash = '{test_case.expected_version_hash}'",
    )[0][0]
    assert (
        postgres_state_backend.get_model_version(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == model_record
    )
    assert replaced_created_at == original_created_at


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendCoreRecordsTestCase(
            description="preserves created_at for physical relations and virtual environments",
            sqlbuild_version="0.0.test",
            expected_model_name="fact_orders",
            expected_version_hash="abc123",
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=["preserves created_at for physical relations and virtual environments"],
)
def test_given_postgres_state_backend_when_replacing_rows_then_preserves_created_at(
    test_case: PostgresStateBackendCoreRecordsTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=test_case.expected_relation_name,
        relation_type="table",
    )
    postgres_state_backend.upsert_physical_relation(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=relation_record,
    )
    physical_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='physical_relations')} "
        f"WHERE model_name = '{test_case.expected_model_name}' "
        f"AND version_hash = '{test_case.expected_version_hash}'",
    )[0][0]
    postgres_state_backend.upsert_physical_relation(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=relation_record,
    )
    replaced_physical_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='physical_relations')} "
        f"WHERE model_name = '{test_case.expected_model_name}' "
        f"AND version_hash = '{test_case.expected_version_hash}'",
    )[0][0]

    virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name=test_case.expected_virtual_environment_name,
        status=VirtualEnvironmentStatus.FINALIZED,
        baseline_virtual_environment_name=None,
    )
    postgres_state_backend.upsert_virtual_environment(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=virtual_environment_record,
    )
    virtual_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='virtual_environments')} "
        f"WHERE virtual_environment_name = '{test_case.expected_virtual_environment_name}'",
    )[0][0]
    postgres_state_backend.upsert_virtual_environment(
        postgres_state_connection,
        schema=postgres_state_schema,
        record=virtual_environment_record,
    )
    replaced_virtual_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='virtual_environments')} "
        f"WHERE virtual_environment_name = '{test_case.expected_virtual_environment_name}'",
    )[0][0]

    assert (
        postgres_state_backend.get_physical_relation(
            postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == relation_record
    )
    assert (
        postgres_state_backend.get_virtual_environment(
            postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
        == virtual_environment_record
    )
    assert replaced_physical_created_at == physical_created_at
    assert replaced_virtual_created_at == virtual_created_at


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendConcurrentLockTestCase(
            description="allows only one winner across two Postgres connections",
            sqlbuild_version="0.0.test",
            lock_key="virtual_env:dev",
            first_owner="run-1",
            second_owner="run-2",
            expected_success_count=1,
            expected_active_lock_count=1,
        )
    ],
    ids=["allows only one winner across two Postgres connections"],
)
def test_given_postgres_state_backend_when_two_connections_acquire_same_lock_then_only_one_succeeds(
    test_case: PostgresStateBackendConcurrentLockTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_config: dict[str, object],
    postgres_state_schema: str,
) -> None:
    second_connection: Any = postgres_state_backend.connect(postgres_state_config)
    try:
        postgres_state_backend.initialize(
            postgres_state_connection,
            schema=postgres_state_schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        future_expiry: datetime = datetime.now() + timedelta(hours=1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures: list[Future[bool]] = [
                executor.submit(
                    postgres_state_backend.acquire_lock,
                    postgres_state_connection,
                    schema=postgres_state_schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.first_owner,
                    expires_at=future_expiry,
                ),
                executor.submit(
                    postgres_state_backend.acquire_lock,
                    second_connection,
                    schema=postgres_state_schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.second_owner,
                    expires_at=future_expiry,
                ),
            ]
        results: list[bool] = [future.result() for future in futures]

        assert sum(1 for result in results if result) == test_case.expected_success_count
        active_locks: tuple[StateLockRecord, ...] = postgres_state_backend.list_active_locks(
            postgres_state_connection,
            schema=postgres_state_schema,
        )
        assert len(active_locks) == test_case.expected_active_lock_count
        assert active_locks[0].owner_id in {test_case.first_owner, test_case.second_owner}
    finally:
        postgres_state_backend.close(second_connection)
