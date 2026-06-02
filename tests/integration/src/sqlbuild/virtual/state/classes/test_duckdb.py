from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from sqlbuild.virtual.state.constants import STATE_TABLE_INDEXES, STATE_TABLES
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    ReconcileEventRecord,
    StateLockRecord,
    StateOperationEventRecord,
    StateOperationRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    ReconcileAction,
    StateMigrationAction,
    StateOperationStatus,
    StateOperationType,
    StateSchemaValidationIssueKind,
    VirtualEnvironmentStatus,
)
from tests.integration.src.sqlbuild.virtual.state.classes._test_types import (
    DuckDbStateBackendConcurrentLockTestCase,
    DuckDbStateBackendCoreRecordsTestCase,
    DuckDbStateBackendErrorTestCase,
    DuckDbStateBackendEventTestCase,
    DuckDbStateBackendIdempotencyTestCase,
    DuckDbStateBackendIndexValidationTestCase,
    DuckDbStateBackendLifecycleTestCase,
    DuckDbStateBackendLockTestCase,
    DuckDbStateBackendOperationEventTestCase,
    DuckDbStateBackendRollbackTestCase,
    DuckDbStateBackendTableCreationTestCase,
    DuckDbStateBackendTransactionRollbackTestCase,
    DuckDbStateBackendValidationTestCase,
)
from tests.integration.src.sqlbuild.virtual.state.classes.helpers import (
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
            expected_issue_count=19,
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
            expected_index_names=tuple(
                sorted(
                    index_name for indexes in STATE_TABLE_INDEXES.values() for index_name in indexes
                )
            ),
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
        assert (
            tuple(
                row[0]
                for row in fetch_all(
                    connection,
                    "SELECT index_name FROM duckdb_indexes() "
                    f"WHERE schema_name = '{test_case.schema}' ORDER BY index_name",
                )
            )
            == test_case.expected_index_names
        )
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


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendTableCreationTestCase(
            description="initializes all phase two state tables",
            schema="sqlbuild_state",
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
def test_given_duckdb_state_backend_when_initializing_then_creates_all_state_tables(
    test_case: DuckDbStateBackendTableCreationTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )

        rows: list[tuple[object, ...]] = fetch_all(
            connection,
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{test_case.schema}' ORDER BY table_name",
        )
        index_rows: list[tuple[object, ...]] = fetch_all(
            connection,
            "SELECT index_name FROM duckdb_indexes() "
            f"WHERE schema_name = '{test_case.schema}' ORDER BY index_name",
        )

        assert tuple(row[0] for row in rows) == test_case.expected_table_names
        assert tuple(row[0] for row in index_rows) == test_case.expected_index_names
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendCoreRecordsTestCase(
            description="persists model physical relation and virtual environment refs",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            expected_model_name="fact_orders",
            expected_version_hash="abc123",
            expected_virtual_target_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=["persists model physical relation and virtual environment refs"],
)
def test_given_duckdb_state_backend_when_upserting_core_records_then_round_trips_state(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        assert (
            backend.get_model_version(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            is None
        )
        assert (
            backend.get_physical_relation(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            is None
        )
        assert (
            backend.get_virtual_environment(
                connection,
                schema=test_case.schema,
                virtual_target_name=test_case.expected_virtual_target_name,
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
        backend.upsert_model_version(connection, schema=test_case.schema, record=model_record)
        relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            database_name=None,
            schema_name="dev__sqb_physical",
            relation_name=test_case.expected_relation_name,
            relation_type="table",
        )
        backend.upsert_physical_relation(
            connection, schema=test_case.schema, record=relation_record
        )
        replaced_relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            database_name=None,
            schema_name="dev__sqb_physical",
            relation_name=test_case.expected_replaced_relation_name,
            relation_type="table",
        )
        backend.upsert_physical_relation(
            connection, schema=test_case.schema, record=replaced_relation_record
        )
        ancestry_record: PhysicalRelationAncestryRecord = PhysicalRelationAncestryRecord(
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            parent_model_name=test_case.expected_model_name,
            parent_version_hash="parent123",
            seed_strategy="copy",
        )
        backend.upsert_physical_relation_ancestry(
            connection, schema=test_case.schema, record=ancestry_record
        )
        virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
            virtual_target_name=test_case.expected_virtual_target_name,
            status=VirtualEnvironmentStatus.FINALIZED,
            baseline_virtual_target_name=None,
        )
        backend.upsert_virtual_environment(
            connection,
            schema=test_case.schema,
            record=virtual_environment_record,
        )
        backend.replace_virtual_environment_refs(
            connection,
            schema=test_case.schema,
            virtual_target_name=test_case.expected_virtual_target_name,
            refs=(
                VirtualEnvironmentRefRecord(
                    virtual_target_name=test_case.expected_virtual_target_name,
                    model_name=test_case.expected_model_name,
                    version_hash=test_case.expected_version_hash,
                ),
            ),
        )

        assert (
            backend.get_model_version(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == model_record
        )
        assert (
            backend.get_physical_relation(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == replaced_relation_record
        )
        assert (
            backend.get_physical_relation_ancestry(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == ancestry_record
        )
        assert (
            backend.get_virtual_environment(
                connection,
                schema=test_case.schema,
                virtual_target_name=test_case.expected_virtual_target_name,
            )
            == virtual_environment_record
        )
        refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
            connection,
            schema=test_case.schema,
            virtual_target_name=test_case.expected_virtual_target_name,
        )
        assert len(refs) == test_case.expected_ref_count
        assert refs[0].model_name == test_case.expected_model_name
        assert refs[0].version_hash == test_case.expected_version_hash
        backend.replace_virtual_environment_refs(
            connection,
            schema=test_case.schema,
            virtual_target_name=test_case.expected_virtual_target_name,
            refs=(),
        )
        replaced_refs: tuple[VirtualEnvironmentRefRecord, ...] = (
            backend.get_virtual_environment_refs(
                connection,
                schema=test_case.schema,
                virtual_target_name=test_case.expected_virtual_target_name,
            )
        )
        assert len(replaced_refs) == test_case.expected_ref_count_after_replace
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendCoreRecordsTestCase(
            description="persists function versions refs and checkpoint refs",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            expected_model_name="is_large_order",
            expected_version_hash="function123",
            expected_virtual_target_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="unused",
            expected_replaced_relation_name="unused",
        )
    ],
    ids=["persists function versions refs and checkpoint refs"],
)
def test_given_duckdb_state_backend_when_upserting_function_records_then_round_trips_state(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        assert (
            backend.get_function_version(
                connection,
                schema=test_case.schema,
                function_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            is None
        )
        function_record: FunctionVersionRecord = FunctionVersionRecord(
            function_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            language="sql",
            returns="BOOLEAN",
            arguments_json_b64="W3sibmFtZSI6ImFtb3VudCIsInR5cGUiOiJJTlRFR0VSIn1d",
            return_columns_json_b64="W10=",
            packages_json_b64="W10=",
            runtime_version=None,
            entry_point=None,
            body_sql_b64="YW1vdW50ID4gOQ==",
            fingerprint_query_sql_b64="YW1vdW50ID4gOQ==",
            status=ModelVersionStatus.READY,
        )
        backend.upsert_function_version(
            connection,
            schema=test_case.schema,
            record=function_record,
        )
        assert (
            backend.get_function_version(
                connection,
                schema=test_case.schema,
                function_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == function_record
        )
        backend.replace_virtual_environment_function_refs(
            connection,
            schema=test_case.schema,
            virtual_target_name=test_case.expected_virtual_target_name,
            refs=(
                VirtualEnvironmentFunctionRefRecord(
                    virtual_target_name=test_case.expected_virtual_target_name,
                    function_name=test_case.expected_model_name,
                    version_hash=test_case.expected_version_hash,
                ),
            ),
        )
        function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (
            backend.get_virtual_environment_function_refs(
                connection,
                schema=test_case.schema,
                virtual_target_name=test_case.expected_virtual_target_name,
            )
        )
        assert len(function_refs) == test_case.expected_ref_count
        assert function_refs[0].function_name == test_case.expected_model_name
        checkpoint: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
            checkpoint_id="chk_function",
            virtual_target_name=test_case.expected_virtual_target_name,
        )
        backend.create_virtual_environment_checkpoint(
            connection,
            schema=test_case.schema,
            checkpoint=checkpoint,
            refs=(),
            function_refs=(
                VirtualEnvironmentCheckpointFunctionRefRecord(
                    checkpoint_id=checkpoint.checkpoint_id,
                    function_name=test_case.expected_model_name,
                    version_hash=test_case.expected_version_hash,
                ),
            ),
        )
        checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (
            backend.get_virtual_environment_checkpoint_function_refs(
                connection,
                schema=test_case.schema,
                checkpoint_id=checkpoint.checkpoint_id,
            )
        )
        assert len(checkpoint_function_refs) == test_case.expected_ref_count
        backend.delete_virtual_environment_checkpoint(
            connection,
            schema=test_case.schema,
            checkpoint_id=checkpoint.checkpoint_id,
        )
        assert (
            backend.get_virtual_environment_checkpoint_function_refs(
                connection,
                schema=test_case.schema,
                checkpoint_id=checkpoint.checkpoint_id,
            )
            == ()
        )
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendLockTestCase(
            description="acquires blocks releases and replaces expired locks",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            lock_key="virtual_env:dev",
            first_owner="run-1",
            second_owner="run-2",
            expected_active_lock_count=1,
        )
    ],
    ids=["acquires blocks releases and replaces expired locks"],
)
def test_given_duckdb_state_backend_when_managing_locks_then_enforces_active_owner(
    test_case: DuckDbStateBackendLockTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        future_expiry: datetime = datetime.now() + timedelta(hours=1)
        expired_at: datetime = datetime.now() - timedelta(hours=1)

        assert backend.acquire_lock(
            connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
            expires_at=future_expiry,
        )
        assert not backend.acquire_lock(
            connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
            expires_at=future_expiry,
        )
        active_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection,
            schema=test_case.schema,
        )
        assert len(active_locks) == test_case.expected_active_lock_count
        assert active_locks[0].owner_id == test_case.first_owner
        assert not backend.release_lock(
            connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
        )
        assert backend.release_lock(
            connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
        )
        assert backend.list_active_locks(connection, schema=test_case.schema) == ()

        assert backend.acquire_lock(
            connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
            expires_at=expired_at,
        )
        assert backend.acquire_lock(
            connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
            expires_at=future_expiry,
        )
        replacement_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection,
            schema=test_case.schema,
        )
        assert len(replacement_locks) == test_case.expected_active_lock_count
        assert replacement_locks[0].owner_id == test_case.second_owner
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendIndexValidationTestCase(
            description="reports missing unique state index",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            dropped_index_name="idx_sqb_locks_identity",
            expected_issue_kind=StateSchemaValidationIssueKind.MISSING_INDEX.value,
        )
    ],
    ids=["reports missing unique state index"],
)
def test_given_duckdb_state_backend_when_required_index_is_missing_then_validation_reports_it(
    test_case: DuckDbStateBackendIndexValidationTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )

        connection.execute(f"DROP INDEX {test_case.schema}.{test_case.dropped_index_name}")

        validation_result: StateSchemaValidationResult = backend.validate_schema(
            connection,
            schema=test_case.schema,
        )

        assert test_case.expected_issue_kind in tuple(
            issue.kind.value for issue in validation_result.issues
        )
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendTransactionRollbackTestCase(
            description="rolls back VDE ref replacement when duplicate rows violate unique index",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            virtual_target_name="dev",
            model_name="fact_orders",
            original_version_hash="abc123",
            duplicate_version_hash="def456",
            expected_ref_count=1,
        )
    ],
    ids=["rolls back VDE ref replacement when duplicate rows violate unique index"],
)
def test_given_duckdb_state_backend_when_ref_replace_fails_then_transaction_rolls_back(
    test_case: DuckDbStateBackendTransactionRollbackTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backend.replace_virtual_environment_refs(
            connection,
            schema=test_case.schema,
            virtual_target_name=test_case.virtual_target_name,
            refs=(
                VirtualEnvironmentRefRecord(
                    virtual_target_name=test_case.virtual_target_name,
                    model_name=test_case.model_name,
                    version_hash=test_case.original_version_hash,
                ),
            ),
        )

        with pytest.raises(duckdb.ConstraintException):
            backend.replace_virtual_environment_refs(
                connection,
                schema=test_case.schema,
                virtual_target_name=test_case.virtual_target_name,
                refs=(
                    VirtualEnvironmentRefRecord(
                        virtual_target_name=test_case.virtual_target_name,
                        model_name=test_case.model_name,
                        version_hash=test_case.original_version_hash,
                    ),
                    VirtualEnvironmentRefRecord(
                        virtual_target_name=test_case.virtual_target_name,
                        model_name=test_case.model_name,
                        version_hash=test_case.duplicate_version_hash,
                    ),
                ),
            )

        refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
            connection,
            schema=test_case.schema,
            virtual_target_name=test_case.virtual_target_name,
        )
        assert len(refs) == test_case.expected_ref_count
        assert refs[0].version_hash == test_case.original_version_hash
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendCoreRecordsTestCase(
            description="preserves created_at across current-state replacements",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            expected_model_name="fact_orders",
            expected_version_hash="abc123",
            expected_virtual_target_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=["preserves created_at across current-state replacements"],
)
def test_given_duckdb_state_backend_when_upserting_same_identity_then_created_at_is_preserved(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        model_record: ModelVersionRecord = ModelVersionRecord(
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            data_hash="data-hash",
            metadata_hash="metadata-hash",
            status=ModelVersionStatus.READY,
        )
        backend.upsert_model_version(connection, schema=test_case.schema, record=model_record)
        original_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.model_versions "
            f"WHERE model_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]

        backend.upsert_model_version(connection, schema=test_case.schema, record=model_record)

        replaced_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.model_versions "
            f"WHERE model_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]
        assert (
            backend.get_model_version(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == model_record
        )
        assert replaced_created_at == original_created_at
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendCoreRecordsTestCase(
            description="preserves created_at for physical relations and virtual environments",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            expected_model_name="fact_orders",
            expected_version_hash="abc123",
            expected_virtual_target_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=["preserves created_at for physical relations and virtual environments"],
)
def test_given_duckdb_state_backend_when_replacing_rows_then_preserves_created_at(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
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
        backend.upsert_physical_relation(
            connection,
            schema=test_case.schema,
            record=relation_record,
        )
        physical_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.physical_relations "
            f"WHERE model_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]
        backend.upsert_physical_relation(
            connection,
            schema=test_case.schema,
            record=relation_record,
        )
        replaced_physical_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.physical_relations "
            f"WHERE model_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]

        virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
            virtual_target_name=test_case.expected_virtual_target_name,
            status=VirtualEnvironmentStatus.FINALIZED,
            baseline_virtual_target_name=None,
        )
        backend.upsert_virtual_environment(
            connection,
            schema=test_case.schema,
            record=virtual_environment_record,
        )
        virtual_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.virtual_environments "
            f"WHERE virtual_target_name = '{test_case.expected_virtual_target_name}'",
        )[0][0]
        backend.upsert_virtual_environment(
            connection,
            schema=test_case.schema,
            record=virtual_environment_record,
        )
        replaced_virtual_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.virtual_environments "
            f"WHERE virtual_target_name = '{test_case.expected_virtual_target_name}'",
        )[0][0]

        assert (
            backend.get_physical_relation(
                connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == relation_record
        )
        assert (
            backend.get_virtual_environment(
                connection,
                schema=test_case.schema,
                virtual_target_name=test_case.expected_virtual_target_name,
            )
            == virtual_environment_record
        )
        assert replaced_physical_created_at == physical_created_at
        assert replaced_virtual_created_at == virtual_created_at
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendOperationEventTestCase(
            description="records operation and reconcile events",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            expected_operation_id="op-1",
            expected_virtual_target_name="dev",
        )
    ],
    ids=["records operation and reconcile events"],
)
def test_given_duckdb_state_backend_when_recording_operation_events_then_they_round_trip(
    test_case: DuckDbStateBackendOperationEventTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backend.upsert_state_operation(
            connection,
            schema=test_case.schema,
            record=StateOperationRecord(
                operation_id=test_case.expected_operation_id,
                operation_type=StateOperationType.PROMOTE,
                status=StateOperationStatus.RUNNING,
                virtual_target_name=test_case.expected_virtual_target_name,
            ),
        )
        backend.create_state_operation_event(
            connection,
            schema=test_case.schema,
            record=StateOperationEventRecord(
                event_id="event-1",
                operation_id=test_case.expected_operation_id,
                action="start",
                status=StateOperationStatus.RUNNING,
                message="started",
            ),
        )
        backend.create_reconcile_event(
            connection,
            schema=test_case.schema,
            record=ReconcileEventRecord(
                event_id="event-2",
                action=ReconcileAction.REPORT,
                status=StateOperationStatus.SUCCEEDED,
                message="clean",
            ),
        )

        assert backend.get_state_operation(
            connection,
            schema=test_case.schema,
            operation_id=test_case.expected_operation_id,
        ) == StateOperationRecord(
            operation_id=test_case.expected_operation_id,
            operation_type=StateOperationType.PROMOTE,
            status=StateOperationStatus.RUNNING,
            virtual_target_name=test_case.expected_virtual_target_name,
        )
        assert fetch_all(
            connection,
            f"SELECT action, status, message FROM {test_case.schema}.state_operation_events "
            f"WHERE operation_id = '{test_case.expected_operation_id}'",
        ) == [("start", "running", "started")]
        assert fetch_all(
            connection,
            f"SELECT action, status, message FROM {test_case.schema}.reconcile_events "
            "WHERE event_id = 'event-2'",
        ) == [("report", "succeeded", "clean")]
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendConcurrentLockTestCase(
            description="allows only one winner across two DuckDB connections",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            lock_key="virtual_env:dev",
            first_owner="run-1",
            second_owner="run-2",
            expected_success_count=1,
            expected_active_lock_count=1,
        )
    ],
    ids=["allows only one winner across two DuckDB connections"],
)
def test_given_duckdb_state_backend_when_two_connections_acquire_same_lock_then_only_one_succeeds(
    test_case: DuckDbStateBackendConcurrentLockTestCase,
    tmp_path: Path,
) -> None:
    db_path: Path = tmp_path / "state.duckdb"
    backend, first_connection = open_duckdb_state_backend(db_path=db_path)
    second_backend, second_connection = open_duckdb_state_backend(db_path=db_path)
    try:
        backend.initialize(
            first_connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        future_expiry: datetime = datetime.now() + timedelta(hours=1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures: list[Future[bool]] = [
                executor.submit(
                    backend.acquire_lock,
                    first_connection,
                    schema=test_case.schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.first_owner,
                    expires_at=future_expiry,
                ),
                executor.submit(
                    second_backend.acquire_lock,
                    second_connection,
                    schema=test_case.schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.second_owner,
                    expires_at=future_expiry,
                ),
            ]
        results: list[bool] = [future.result() for future in futures]

        assert sum(1 for result in results if result) == test_case.expected_success_count
        active_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            first_connection,
            schema=test_case.schema,
        )
        assert len(active_locks) == test_case.expected_active_lock_count
        assert active_locks[0].owner_id in {test_case.first_owner, test_case.second_owner}
    finally:
        backend.close(first_connection)
        second_backend.close(second_connection)
