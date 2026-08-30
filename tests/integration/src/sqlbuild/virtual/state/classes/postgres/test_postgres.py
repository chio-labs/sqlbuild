from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import pytest

from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.executor.node_results.types import NodeResultStatus
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
from sqlbuild.microbatches.types import (
    MicrobatchCompletionType,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
)
from sqlbuild.virtual.state.classes.postgres import PostgresStateBackend
from sqlbuild.virtual.state.constants import STATE_TABLE_INDEXES, STATE_TABLES
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    PythonNodeVersionRecord,
    ReconcileEventRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    StateLockLease,
    StateLockRecord,
    StateOperationEventRecord,
    StateOperationRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentPythonNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    PhysicalArtifactType,
    ReconcileAction,
    StateMigrationAction,
    StateOperationStatus,
    StateOperationType,
    StateSchemaValidationIssueKind,
    VirtualEnvironmentStatus,
)
from tests.integration.src.sqlbuild.virtual.state.classes.helpers import (
    ACTIVE_CHECKPOINT_PAYLOAD,
    ACTIVE_PAYLOAD,
    CHECKPOINT_DUPLICATE_PAYLOAD,
    CHECKPOINT_ENVIRONMENT_PAYLOAD,
    CHECKPOINT_ID_PAYLOAD,
    FUNCTION_OMISSION_PAYLOAD,
    MISSING_CHECKPOINT_PAYLOAD,
    MODEL_VERSION_PAYLOAD,
    ORPHAN_CHECKPOINT_REFS_PAYLOAD,
    PUBLISHED_DUPLICATE_PAYLOAD,
    REF_ENVIRONMENT_PAYLOAD,
    REF_NODE_TYPE_PAYLOAD,
    SEED_EXTRA_PAYLOAD,
    VALID_PAYLOAD,
)
from tests.integration.src.sqlbuild.virtual.state.classes.postgres._test_types import (
    PostgresAtomicFinalizedVirtualPublishTestCase,
    PostgresConditionalPublicationPayloadContractTestCase,
    PostgresConditionalVirtualRefPublishTestCase,
    PostgresMicrobatchStateRoundTripTestCase,
    PostgresStateBackendColumnValidationTestCase,
    PostgresStateBackendConcurrentLockTestCase,
    PostgresStateBackendCoreRecordsTestCase,
    PostgresStateBackendErrorTestCase,
    PostgresStateBackendExplicitRollbackTestCase,
    PostgresStateBackendIndexValidationTestCase,
    PostgresStateBackendLifecycleTestCase,
    PostgresStateBackendLockTestCase,
    PostgresStateBackendNodeResultTestCase,
    PostgresStateBackendOperationEventTestCase,
    PostgresStateBackendPythonNodeIdentityTestCase,
    PostgresStateBackendSeedRefTestCase,
    PostgresStateBackendSourceFreshnessTestCase,
    PostgresStateBackendTableCreationTestCase,
    PostgresStateBackendTransactionRollbackTestCase,
    PostgresStateBackendValidationTestCase,
)
from tests.integration.src.sqlbuild.virtual.state.classes.postgres.helpers import (
    fetch_all,
    qualified_name,
    quote_identifier,
)

EXPECTED_STATE_INDEX_NAMES: list[str] = []
for state_indexes in STATE_TABLE_INDEXES.values():
    for state_index_name in state_indexes:
        EXPECTED_STATE_INDEX_NAMES.append(state_index_name)
EXPECTED_STATE_INDEX_NAMES.sort()


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresConditionalPublicationPayloadContractTestCase(
            description="postgres exact finalized payload succeeds",
            payload=VALID_PAYLOAD,
            expected_valid=True,
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            description="postgres active payload without checkpoint succeeds",
            payload=ACTIVE_PAYLOAD,
            expected_valid=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_conditional_payload_when_postgres_publishes_then_contract_succeeds(
    test_case: PostgresConditionalPublicationPayloadContractTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="test",
    )
    assert (
        postgres_state_backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            record=test_case.payload.record,
            refs_by_node_type=test_case.payload.refs_by_node_type,
            leases=(),
            checkpoint=test_case.payload.checkpoint,
            checkpoint_refs=test_case.payload.checkpoint_refs,
            checkpoint_function_refs=test_case.payload.checkpoint_function_refs,
            checkpoint_seed_refs=test_case.payload.checkpoint_seed_refs,
        )
        is test_case.expected_valid
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres finalized requires checkpoint",
            MISSING_CHECKPOINT_PAYLOAD,
            False,
            "requires a checkpoint",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres active forbids checkpoint",
            ACTIVE_CHECKPOINT_PAYLOAD,
            False,
            "forbids checkpoint",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres refs require checkpoint",
            ORPHAN_CHECKPOINT_REFS_PAYLOAD,
            False,
            "refs require a checkpoint",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres checkpoint environment matches",
            CHECKPOINT_ENVIRONMENT_PAYLOAD,
            False,
            "match the published environment",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres checkpoint ids match",
            CHECKPOINT_ID_PAYLOAD,
            False,
            "checkpoint_id must match",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres model refs correspond",
            MODEL_VERSION_PAYLOAD,
            False,
            "model refs must exactly match",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres function refs have no omissions",
            FUNCTION_OMISSION_PAYLOAD,
            False,
            "function refs must exactly match",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres seed refs have no extras",
            SEED_EXTRA_PAYLOAD,
            False,
            "seed refs must exactly match",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres checkpoint refs have no duplicates",
            CHECKPOINT_DUPLICATE_PAYLOAD,
            False,
            "duplicate identities",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres current refs have no duplicates",
            PUBLISHED_DUPLICATE_PAYLOAD,
            False,
            "duplicate identities",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres ref environment matches",
            REF_ENVIRONMENT_PAYLOAD,
            False,
            "virtual_environment_name",
        ),
        PostgresConditionalPublicationPayloadContractTestCase(
            "postgres ref group matches node type",
            REF_NODE_TYPE_PAYLOAD,
            False,
            "node_type must match",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_conditional_payload_when_postgres_publishes_then_contract_rejects_before_write(
    test_case: PostgresConditionalPublicationPayloadContractTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="test",
    )
    with pytest.raises(StateBackendConfigError, match=test_case.expected_error_fragment or ""):
        postgres_state_backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            record=test_case.payload.record,
            refs_by_node_type=test_case.payload.refs_by_node_type,
            leases=(),
            checkpoint=test_case.payload.checkpoint,
            checkpoint_refs=test_case.payload.checkpoint_refs,
            checkpoint_function_refs=test_case.payload.checkpoint_function_refs,
            checkpoint_seed_refs=test_case.payload.checkpoint_seed_refs,
        )

    assert test_case.expected_valid is False
    assert (
        postgres_state_backend.get_virtual_environment(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.payload.record.virtual_environment_name,
        )
        is None
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresMicrobatchStateRoundTripTestCase(
            description="postgres events are idempotent",
            expected_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_microbatch_event_when_appending_then_scope_history_round_trips(
    test_case: PostgresMicrobatchStateRoundTripTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="test",
    )
    scope: MicrobatchScope = MicrobatchScope(
        scope_kind="virtual_physical",
        scope_key="postgres:state:orders:F2:analytics.orders__F2",
        model_name="orders",
        target_database="warehouse",
        target_schema="analytics",
        target_name="orders__F2",
        physical_generation_id="F2:analytics.orders__F2",
        virtual_environment_name="dev",
        virtual_model_version_hash="F2",
    )
    event: MicrobatchEvent = MicrobatchEvent(
        event_id="event-1",
        record_type=MicrobatchRecordType.PARTITION_COMPLETION,
        scope=scope,
        origin_run_id="run-1",
        execution_run_id="run-1",
        run_type=MicrobatchRunType.NORMAL,
        completion_type=MicrobatchCompletionType.INITIAL,
        run_start="0",
        run_end="1",
        partition_start="0",
        partition_end="1",
        batch_size="1",
        cursor_column="batch_id",
        cursor_type="integer",
        model_version_hash="F2",
        definition_hash="definition",
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        rows_affected=0,
        created_at=datetime(2026, 1, 1),
    )

    postgres_state_backend.append_microbatch_event(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        event=event,
    )
    postgres_state_backend.append_microbatch_event(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        event=event,
    )

    history: tuple[MicrobatchEvent, ...] = postgres_state_backend.read_microbatch_scope_history(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        scope=scope,
    )
    retention_history: tuple[MicrobatchEvent, ...] = (
        postgres_state_backend.read_microbatch_retention_history(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
        )
    )
    model_history: tuple[MicrobatchEvent, ...] = (
        postgres_state_backend.read_microbatch_model_history(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            scope=scope,
        )
    )
    assert len(history) == test_case.expected_event_count
    assert history == (event,)
    assert retention_history == history
    assert model_history == history


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
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_running_lifecycle_then_state_tables_are_managed(
    test_case: PostgresStateBackendLifecycleTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    assert fetch_all(
        postgres_state_connection,
        "SELECT schema_version FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_versions')}",
    ) == [(test_case.expected_schema_version,)]
    assert postgres_state_backend.inspect_schema(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    ).valid

    backup_id: str = postgres_state_backend.create_backup(
        connection=postgres_state_connection,
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
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert rolled_back_backup_id == backup_id
    assert fetch_all(
        postgres_state_connection,
        "SELECT action FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_migration_events')} "
        "ORDER BY created_at",
    ) == [(action,) for action in test_case.expected_actions_after_rollback]

    postgres_state_backend.reset(connection=postgres_state_connection, schema=postgres_state_schema)
    validation_after_reset: StateSchemaValidationResult = postgres_state_backend.inspect_schema(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert not validation_after_reset.valid


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendValidationTestCase(
            description="reports invalid manually-created state schema",
            expected_issue_count=24,
        )
    ],
    ids=lambda case: case.description,
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

    result: StateSchemaValidationResult = postgres_state_backend.inspect_schema(
        connection=postgres_state_connection,
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
    ids=lambda case: case.description,
)
def test_given_postgres_state_without_backup_when_rolling_back_then_blocks_cleanly(
    test_case: PostgresStateBackendErrorTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="0.0.test",
    )

    with pytest.raises(test_case.expected_error_type) as exc_info:
        postgres_state_backend.rollback(
            connection=postgres_state_connection, schema=postgres_state_schema
        )

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
    ids=lambda case: case.description,
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
            connection=postgres_state_connection, schema=postgres_state_schema
        )

    assert test_case.expected_message_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendExplicitRollbackTestCase(
            description="rolls back to explicitly selected backup",
            sqlbuild_version="0.0.test",
            expected_restored_schema_version=1,
            expected_index_names=tuple(EXPECTED_STATE_INDEX_NAMES),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_state_backups_when_rolling_back_explicit_id_then_restores_backup(
    test_case: PostgresStateBackendExplicitRollbackTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    first_backup_id: str = postgres_state_backend.create_backup(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    )
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            "UPDATE "
            f"{qualified_name(schema=postgres_state_schema, table='state_versions')} "
            "SET schema_version = 2"
        )
    postgres_state_backend.create_backup(
        connection=postgres_state_connection, schema=postgres_state_schema
    )
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {qualified_name(schema=postgres_state_schema, table='state_versions')}"
        )

    postgres_state_backend.rollback(
        connection=postgres_state_connection,
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
            expected_index_names=tuple(EXPECTED_STATE_INDEX_NAMES),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_initializing_then_creates_all_state_tables(
    test_case: PostgresStateBackendTableCreationTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
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
            description="reports missing node results latest index",
            sqlbuild_version="0.0.test",
            dropped_index_name="idx_sqb_node_results_latest",
            expected_issue_kind=StateSchemaValidationIssueKind.MISSING_INDEX.value,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_required_index_is_missing_then_validation_reports_it(
    test_case: PostgresStateBackendIndexValidationTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )

    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            "DROP INDEX "
            f"{qualified_name(schema=postgres_state_schema, table=test_case.dropped_index_name)}"
        )

    validation_result: StateSchemaValidationResult = postgres_state_backend.inspect_schema(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    )

    assert test_case.expected_issue_kind in tuple(
        issue.kind.value for issue in validation_result.issues
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendColumnValidationTestCase(
            description="reports missing node results payload column",
            sqlbuild_version="0.0.test",
            dropped_table_name="node_results",
            dropped_column_name="payload_json_b64",
            expected_issue_kind=StateSchemaValidationIssueKind.MISSING_COLUMN.value,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_node_results_column_missing_then_validation_reports_it(
    test_case: PostgresStateBackendColumnValidationTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )

    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            "ALTER TABLE "
            f"{qualified_name(schema=postgres_state_schema, table=test_case.dropped_table_name)} "
            f"DROP COLUMN {quote_identifier(test_case.dropped_column_name)}"
        )

    validation_result: StateSchemaValidationResult = postgres_state_backend.inspect_schema(
        connection=postgres_state_connection,
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
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_upserting_core_records_then_round_trips_state(
    test_case: PostgresStateBackendCoreRecordsTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    assert (
        postgres_state_backend.get_model_version(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        is None
    )
    assert (
        postgres_state_backend.get_physical_relation(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        is None
    )
    assert (
        postgres_state_backend.get_virtual_environment(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
        is None
    )
    model_record: ModelVersionRecord = ModelVersionRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        definition_identity_hash="definition-identity-hash",
        identity_metadata_hash="identity-metadata-hash",
        status=ModelVersionStatus.READY,
        definition_text_b64="U0VMRUNUIDEgQVMgaWQ=",
        identity_metadata_json_b64="e30=",
        compiled_sql_b64="U0VMRUNUIDEgQVMgaWQ=",
    )
    postgres_state_backend.upsert_model_version(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=model_record,
    )
    relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=test_case.expected_relation_name,
        relation_type="table",
    )
    postgres_state_backend.upsert_physical_relation(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=relation_record,
    )
    replaced_relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=test_case.expected_replaced_relation_name,
        relation_type="table",
    )
    postgres_state_backend.upsert_physical_relation(
        connection=postgres_state_connection,
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
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=ancestry_record,
    )
    virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name=test_case.expected_virtual_environment_name,
        status=VirtualEnvironmentStatus.FINALIZED,
        baseline_virtual_environment_name=None,
    )
    postgres_state_backend.upsert_virtual_environment(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=virtual_environment_record,
    )
    postgres_state_backend.replace_virtual_environment_model_refs(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.expected_virtual_environment_name,
        refs=(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=test_case.expected_virtual_environment_name,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            ),
        ),
    )

    assert (
        postgres_state_backend.get_model_version(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == model_record
    )
    assert (
        postgres_state_backend.get_physical_relation(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == replaced_relation_record
    )
    assert (
        postgres_state_backend.get_physical_relation_ancestry(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == ancestry_record
    )
    assert (
        postgres_state_backend.get_virtual_environment(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
        == virtual_environment_record
    )
    refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_model_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
    )
    assert len(refs) == test_case.expected_ref_count
    assert refs[0].model_name == test_case.expected_model_name
    assert refs[0].version_hash == test_case.expected_version_hash
    postgres_state_backend.replace_virtual_environment_model_refs(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.expected_virtual_environment_name,
        refs=(),
    )
    replaced_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_model_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
    )
    assert len(replaced_refs) == test_case.expected_ref_count_after_replace


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendSourceFreshnessTestCase(
            description="persists and replaces source freshness observations",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            expected_source_names=("raw.customers", "raw.orders"),
            expected_source_names_after_replace=("raw.orders",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_backend_when_replacing_source_freshness_then_round_trips_records(
    test_case: PostgresStateBackendSourceFreshnessTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    postgres_state_backend.upsert_virtual_environment(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=VirtualEnvironmentRecord(
            virtual_environment_name=test_case.virtual_environment_name,
            status=VirtualEnvironmentStatus.ACTIVE,
        ),
    )
    first_observed_at: datetime = datetime(2026, 1, 1, 12, 0, 0)
    second_observed_at: datetime = datetime(2026, 1, 2, 12, 0, 0)
    postgres_state_backend.replace_virtual_environment_source_freshness(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        records=(
            SourceFreshnessRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                source_name="raw.orders",
                strategy="column",
                value_kind="integer",
                data_version="1",
                data_version_hash="hash-1",
                observed_at=first_observed_at,
            ),
            SourceFreshnessRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                source_name="raw.customers",
                strategy="sql",
                value_kind="string",
                data_version="batch-1",
                data_version_hash="hash-2",
                observed_at=first_observed_at,
            ),
        ),
    )

    records: tuple[SourceFreshnessRecord, ...] = (
        postgres_state_backend.get_virtual_environment_source_freshness(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
    )
    assert tuple(record.source_name for record in records) == test_case.expected_source_names

    postgres_state_backend.replace_virtual_environment_source_freshness(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        records=(
            SourceFreshnessRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                source_name="raw.orders",
                strategy="column",
                value_kind="integer",
                data_version="2",
                data_version_hash="hash-3",
                observed_at=second_observed_at,
            ),
        ),
    )

    replaced_records: tuple[SourceFreshnessRecord, ...] = (
        postgres_state_backend.get_virtual_environment_source_freshness(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
    )
    assert tuple(record.source_name for record in replaced_records) == (
        test_case.expected_source_names_after_replace
    )
    assert replaced_records[0].data_version == "2"
    assert replaced_records[0].data_version_hash == "hash-3"
    assert replaced_records[0].observed_at == second_observed_at

    postgres_state_backend.delete_virtual_environment(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
    )
    assert (
        postgres_state_backend.get_virtual_environment_source_freshness(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
        == ()
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendSeedRefTestCase(
            description="persists seed versions and replaces seed refs",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            seed_name="country_codes",
            version_hash="seed123",
            identity_metadata_hash="meta123",
            identity_metadata_json_b64="e30=",
            expected_ref_count_after_replace=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_backend_when_replacing_seed_refs_then_round_trips_records(
    test_case: PostgresStateBackendSeedRefTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    seed_version: SeedVersionRecord = SeedVersionRecord(
        seed_name=test_case.seed_name,
        version_hash=test_case.version_hash,
        identity_metadata_hash=test_case.identity_metadata_hash,
        identity_metadata_json_b64=test_case.identity_metadata_json_b64,
        status=ModelVersionStatus.READY,
    )
    postgres_state_backend.upsert_seed_version(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=seed_version,
    )
    postgres_state_backend.replace_virtual_environment_seed_refs(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        refs=(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                seed_name=test_case.seed_name,
                version_hash=test_case.version_hash,
            ),
        ),
    )

    assert (
        postgres_state_backend.get_seed_version(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            seed_name=test_case.seed_name,
            version_hash=test_case.version_hash,
        )
        == seed_version
    )
    refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_seed_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
    )
    assert refs == (
        VirtualEnvironmentSeedRefRecord(
            virtual_environment_name=test_case.virtual_environment_name,
            seed_name=test_case.seed_name,
            version_hash=test_case.version_hash,
        ),
    )

    postgres_state_backend.replace_virtual_environment_seed_refs(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        refs=(),
    )
    assert (
        len(
            postgres_state_backend.get_virtual_environment_seed_refs(
                connection=postgres_state_connection,
                schema=postgres_state_schema,
                virtual_environment_name=test_case.virtual_environment_name,
            )
        )
        == test_case.expected_ref_count_after_replace
    )
    postgres_state_backend.replace_virtual_environment_seed_refs(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        refs=(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                seed_name=test_case.seed_name,
                version_hash=test_case.version_hash,
            ),
        ),
    )
    postgres_state_backend.delete_virtual_environment(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
    )
    assert (
        postgres_state_backend.get_virtual_environment_seed_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
        == ()
    )

    checkpoint: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
        checkpoint_id="chk_seed",
        virtual_environment_name=test_case.virtual_environment_name,
    )
    postgres_state_backend.create_virtual_environment_checkpoint(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        checkpoint=checkpoint,
        refs=(),
        seed_refs=(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id=checkpoint.checkpoint_id,
                seed_name=test_case.seed_name,
                version_hash=test_case.version_hash,
            ),
        ),
    )
    checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_checkpoint_seed_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            checkpoint_id=checkpoint.checkpoint_id,
        )
    )
    assert checkpoint_seed_refs == (
        VirtualEnvironmentCheckpointSeedRefRecord(
            checkpoint_id=checkpoint.checkpoint_id,
            seed_name=test_case.seed_name,
            version_hash=test_case.version_hash,
        ),
    )
    postgres_state_backend.delete_virtual_environment_checkpoint(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        checkpoint_id=checkpoint.checkpoint_id,
    )
    assert (
        postgres_state_backend.get_virtual_environment_checkpoint_seed_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            checkpoint_id=checkpoint.checkpoint_id,
        )
        == ()
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendPythonNodeIdentityTestCase(
            description="persists python node versions and separate VDE refs",
            sqlbuild_version="0.0.test",
            first_virtual_environment_name="dev_alice",
            second_virtual_environment_name="dev_bob",
            node_type="task",
            node_name="prepare_orders",
            first_version_hash="version-one",
            second_version_hash="version-two",
            expected_ref_versions=("version-one", "version-two"),
            orphan_version_hash="version-orphan",
            expected_pruned_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_upserting_python_node_identity_then_round_trips_refs(
    test_case: PostgresStateBackendPythonNodeIdentityTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    first_record: PythonNodeVersionRecord = PythonNodeVersionRecord(
        node_type=test_case.node_type,
        node_name=test_case.node_name,
        version_hash=test_case.first_version_hash,
        definition_hash="definition-one",
        identity_metadata_hash="metadata-one",
        definition_json_b64="e30=",
        identity_metadata_json_b64="e30=",
        status=ModelVersionStatus.READY,
    )
    second_record: PythonNodeVersionRecord = PythonNodeVersionRecord(
        node_type=test_case.node_type,
        node_name=test_case.node_name,
        version_hash=test_case.second_version_hash,
        definition_hash="definition-two",
        identity_metadata_hash="metadata-two",
        definition_json_b64="e30=",
        identity_metadata_json_b64="e30=",
        status=ModelVersionStatus.READY,
    )
    orphan_record: PythonNodeVersionRecord = PythonNodeVersionRecord(
        node_type=test_case.node_type,
        node_name=test_case.node_name,
        version_hash=test_case.orphan_version_hash,
        definition_hash="definition-orphan",
        identity_metadata_hash="metadata-orphan",
        definition_json_b64="e30=",
        identity_metadata_json_b64="e30=",
        status=ModelVersionStatus.READY,
    )

    postgres_state_backend.upsert_python_node_version(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=first_record,
    )
    postgres_state_backend.upsert_python_node_version(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=second_record,
    )
    postgres_state_backend.upsert_python_node_version(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=orphan_record,
    )
    postgres_state_backend.upsert_virtual_environment_python_node_ref(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        ref=VirtualEnvironmentPythonNodeRefRecord(
            virtual_environment_name=test_case.first_virtual_environment_name,
            node_type=test_case.node_type,
            node_name=test_case.node_name,
            version_hash=test_case.first_version_hash,
        ),
    )
    postgres_state_backend.upsert_virtual_environment_python_node_ref(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        ref=VirtualEnvironmentPythonNodeRefRecord(
            virtual_environment_name=test_case.second_virtual_environment_name,
            node_type=test_case.node_type,
            node_name=test_case.node_name,
            version_hash=test_case.second_version_hash,
        ),
    )

    first_refs: tuple[VirtualEnvironmentPythonNodeRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_python_node_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.first_virtual_environment_name,
        )
    )
    second_refs: tuple[VirtualEnvironmentPythonNodeRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_python_node_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.second_virtual_environment_name,
        )
    )

    assert (
        postgres_state_backend.get_python_node_version(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            node_type=test_case.node_type,
            node_name=test_case.node_name,
            version_hash=test_case.first_version_hash,
        )
        == first_record
    )
    assert tuple(ref.version_hash for ref in (*first_refs, *second_refs)) == (
        test_case.expected_ref_versions
    )
    assert (
        postgres_state_backend.count_unreferenced_python_node_versions(
            connection=postgres_state_connection, schema=postgres_state_schema
        )
        == test_case.expected_pruned_count
    )
    assert (
        postgres_state_backend.prune_unreferenced_python_node_versions(
            connection=postgres_state_connection, schema=postgres_state_schema
        )
        == test_case.expected_pruned_count
    )
    assert (
        postgres_state_backend.get_python_node_version(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            node_type=test_case.node_type,
            node_name=test_case.node_name,
            version_hash=test_case.orphan_version_hash,
        )
        is None
    )
    assert (
        postgres_state_backend.get_python_node_version(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            node_type=test_case.node_type,
            node_name=test_case.node_name,
            version_hash=test_case.second_version_hash,
        )
        == second_record
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendNodeResultTestCase(
            description="stores and reads VDE node result history by environment",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            isolated_virtual_environment_name="pr_1",
            expected_latest_payload={"value": 2},
            expected_failed_status="failed",
            expected_history_count=2,
            expected_target_isolated_payload={"value": 99},
            expected_rollback_row_count=5,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_node_results_when_reading_then_scopes_by_environment_and_status(
    test_case: PostgresStateBackendNodeResultTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    first_record: NodeResultRecord = NodeResultRecord(
        node_type="task",
        node_name="produce_result",
        target_database=None,
        target_schema="dev",
        target_name=None,
        run_id="run_1",
        status=NodeResultStatus.SUCCESS.value,
        payload={"value": 1},
        metadata={"source": "first"},
        error_message=None,
        materialized=None,
        ts=datetime(2026, 1, 1, 12, 0, 0),
    )
    postgres_state_backend.insert_node_result(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        record=first_record,
    )
    postgres_state_backend.insert_node_result(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        record=NodeResultRecord(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="dev",
            target_name=None,
            run_id="run_2",
            status=NodeResultStatus.SUCCESS.value,
            payload=test_case.expected_latest_payload,
            metadata={"source": "second"},
            error_message=None,
            materialized=None,
            ts=datetime(2026, 1, 1, 12, 1, 0),
        ),
    )
    postgres_state_backend.insert_node_result(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        record=NodeResultRecord(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="dev",
            target_name=None,
            run_id="run_3",
            status=NodeResultStatus.FAILED.value,
            payload=None,
            metadata={},
            error_message="boom",
            materialized=None,
            ts=datetime(2026, 1, 1, 12, 2, 0),
        ),
    )
    postgres_state_backend.insert_node_result(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.isolated_virtual_environment_name,
        record=first_record,
    )
    postgres_state_backend.insert_node_result(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        record=NodeResultRecord(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="prod",
            target_name=None,
            run_id="run_4",
            status=NodeResultStatus.SUCCESS.value,
            payload=test_case.expected_target_isolated_payload,
            metadata={"source": "target"},
            error_message=None,
            materialized=None,
            ts=datetime(2026, 1, 1, 12, 3, 0),
        ),
    )
    backup_id: str = postgres_state_backend.create_backup(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    )
    with postgres_state_connection.cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {qualified_name(schema=postgres_state_schema, table='node_results')}"
        )
    postgres_state_backend.rollback(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        backup_id=backup_id,
    )

    latest_success: tuple[NodeResultEnvelope, ...] = postgres_state_backend.read_node_results(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        query=NodeResultQuery(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="dev",
            target_name=None,
            statuses=(NodeResultStatus.SUCCESS.value,),
            run_id=None,
            limit=1,
        ),
    )
    explicit_failed: tuple[NodeResultEnvelope, ...] = postgres_state_backend.read_node_results(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        query=NodeResultQuery(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="dev",
            target_name=None,
            statuses=None,
            run_id="run_3",
            limit=1,
        ),
    )
    isolated_results: tuple[NodeResultEnvelope, ...] = postgres_state_backend.read_node_results(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.isolated_virtual_environment_name,
        query=NodeResultQuery(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="dev",
            target_name=None,
            statuses=(NodeResultStatus.SUCCESS.value,),
            run_id=None,
            limit=5,
        ),
    )
    history_results: tuple[NodeResultEnvelope, ...] = postgres_state_backend.read_node_results(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        query=NodeResultQuery(
            node_type="task",
            node_name="produce_result",
            target_database=None,
            target_schema="dev",
            target_name=None,
            statuses=(NodeResultStatus.SUCCESS.value,),
            run_id=None,
            limit=5,
        ),
    )
    target_isolated_results: tuple[NodeResultEnvelope, ...] = (
        postgres_state_backend.read_node_results(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
            query=NodeResultQuery(
                node_type="task",
                node_name="produce_result",
                target_database=None,
                target_schema="prod",
                target_name=None,
                statuses=(NodeResultStatus.SUCCESS.value,),
                run_id=None,
                limit=1,
            ),
        )
    )
    rollback_rows: list[tuple[object, ...]] = fetch_all(
        postgres_state_connection,
        "SELECT COUNT(*) FROM "
        f"{qualified_name(schema=postgres_state_schema, table='node_results')}",
    )

    assert latest_success[0].payload == test_case.expected_latest_payload
    assert explicit_failed[0].status == test_case.expected_failed_status
    assert len(isolated_results) == 1
    assert len(history_results) == test_case.expected_history_count
    assert target_isolated_results[0].payload == test_case.expected_target_isolated_payload
    assert rollback_rows == [(test_case.expected_rollback_row_count,)]


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendErrorTestCase(
            description="blocks mismatched source freshness virtual environment",
            expected_error_type=Exception,
            expected_message_fragment="must match replacement virtual_environment_name",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mismatched_postgres_source_freshness_record_when_replacing_then_blocks_cleanly(
    test_case: PostgresStateBackendErrorTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="0.0.test",
    )
    record: SourceFreshnessRecord = SourceFreshnessRecord(
        virtual_environment_name="other",
        source_name="raw.orders",
        strategy="column",
        value_kind="integer",
        data_version="1",
        data_version_hash="hash-1",
        observed_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    with pytest.raises(test_case.expected_error_type) as exc_info:
        postgres_state_backend.replace_virtual_environment_source_freshness(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
            records=(record,),
        )

    assert test_case.expected_message_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresStateBackendErrorTestCase(
            description="blocks duplicate source freshness records",
            expected_error_type=Exception,
            expected_message_fragment="Duplicate source freshness record",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_postgres_source_freshness_records_when_replacing_then_blocks_cleanly(
    test_case: PostgresStateBackendErrorTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="0.0.test",
    )
    records: tuple[SourceFreshnessRecord, ...] = (
        SourceFreshnessRecord(
            virtual_environment_name="dev",
            source_name="raw.orders",
            strategy="column",
            value_kind="integer",
            data_version="1",
            data_version_hash="hash-1",
            observed_at=datetime(2026, 1, 1, 12, 0, 0),
        ),
        SourceFreshnessRecord(
            virtual_environment_name="dev",
            source_name="raw.orders",
            strategy="sql",
            value_kind="string",
            data_version="batch-1",
            data_version_hash="hash-2",
            observed_at=datetime(2026, 1, 1, 12, 0, 0),
        ),
    )
    with pytest.raises(test_case.expected_error_type) as exc_info:
        postgres_state_backend.replace_virtual_environment_source_freshness(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
            records=records,
        )

    assert test_case.expected_message_fragment in str(exc_info.value)


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
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_managing_locks_then_enforces_active_owner(
    test_case: PostgresStateBackendLockTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    future_expiry: datetime = datetime.now() + timedelta(hours=1)
    expired_at: datetime = datetime.now() - timedelta(hours=1)

    assert postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.first_owner,
        expires_at=future_expiry,
    )
    assert not postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.second_owner,
        expires_at=future_expiry,
    )
    active_locks: tuple[StateLockRecord, ...] = postgres_state_backend.list_active_locks(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
    )
    assert len(active_locks) == test_case.expected_active_lock_count
    assert active_locks[0].owner_id == test_case.first_owner
    assert not postgres_state_backend.release_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.second_owner,
    )
    assert postgres_state_backend.release_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.first_owner,
    )
    assert (
        postgres_state_backend.list_active_locks(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
        )
        == ()
    )
    assert postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.first_owner,
        expires_at=expired_at,
    )
    assert postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=test_case.lock_key,
        owner_id=test_case.second_owner,
        expires_at=future_expiry,
    )
    replacement_locks: tuple[StateLockRecord, ...] = postgres_state_backend.list_active_locks(
        connection=postgres_state_connection,
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
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_ref_replace_fails_then_transaction_rolls_back(
    test_case: PostgresStateBackendTransactionRollbackTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    postgres_state_backend.replace_virtual_environment_model_refs(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        virtual_environment_name=test_case.virtual_environment_name,
        refs=(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                model_name=test_case.model_name,
                version_hash=test_case.original_version_hash,
            ),
        ),
    )

    with pytest.raises(StateBackendConfigError):
        postgres_state_backend.replace_virtual_environment_model_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name=test_case.virtual_environment_name,
            refs=(
                VirtualEnvironmentModelRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    model_name=test_case.model_name,
                    version_hash=test_case.original_version_hash,
                ),
                VirtualEnvironmentModelRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    model_name=test_case.model_name,
                    version_hash=test_case.duplicate_version_hash,
                ),
            ),
        )

    refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        postgres_state_backend.get_virtual_environment_model_refs(
            connection=postgres_state_connection,
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
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_upserting_same_identity_then_created_at_is_preserved(
    test_case: PostgresStateBackendCoreRecordsTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    model_record: ModelVersionRecord = ModelVersionRecord(
        model_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        definition_identity_hash="definition-identity-hash",
        identity_metadata_hash="identity-metadata-hash",
        status=ModelVersionStatus.READY,
    )
    postgres_state_backend.upsert_model_version(
        connection=postgres_state_connection,
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
        connection=postgres_state_connection,
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
            connection=postgres_state_connection,
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
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_replacing_rows_then_preserves_created_at(
    test_case: PostgresStateBackendCoreRecordsTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    relation_record: PhysicalRelationRecord = PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name=test_case.expected_model_name,
        version_hash=test_case.expected_version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=test_case.expected_relation_name,
        relation_type="table",
    )
    postgres_state_backend.upsert_physical_relation(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=relation_record,
    )
    physical_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='physical_relations')} "
        "WHERE artifact_type = 'model' "
        f"AND artifact_name = '{test_case.expected_model_name}' "
        f"AND version_hash = '{test_case.expected_version_hash}'",
    )[0][0]
    postgres_state_backend.upsert_physical_relation(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=relation_record,
    )
    replaced_physical_created_at: datetime = fetch_all(
        postgres_state_connection,
        "SELECT created_at FROM "
        f"{qualified_name(schema=postgres_state_schema, table='physical_relations')} "
        "WHERE artifact_type = 'model' "
        f"AND artifact_name = '{test_case.expected_model_name}' "
        f"AND version_hash = '{test_case.expected_version_hash}'",
    )[0][0]

    virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name=test_case.expected_virtual_environment_name,
        status=VirtualEnvironmentStatus.FINALIZED,
        baseline_virtual_environment_name=None,
    )
    postgres_state_backend.upsert_virtual_environment(
        connection=postgres_state_connection,
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
        connection=postgres_state_connection,
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
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
        )
        == relation_record
    )
    assert (
        postgres_state_backend.get_virtual_environment(
            connection=postgres_state_connection,
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
        PostgresStateBackendOperationEventTestCase(
            description="records operation and reconcile events",
            sqlbuild_version="0.0.test",
            expected_operation_id="op-1",
            expected_virtual_environment_name="dev",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_postgres_state_backend_when_recording_operation_events_then_they_round_trip(
    test_case: PostgresStateBackendOperationEventTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version=test_case.sqlbuild_version,
    )
    postgres_state_backend.upsert_state_operation(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=StateOperationRecord(
            operation_id=test_case.expected_operation_id,
            operation_type=StateOperationType.PROMOTE,
            status=StateOperationStatus.RUNNING,
            virtual_environment_name=test_case.expected_virtual_environment_name,
        ),
    )
    postgres_state_backend.create_state_operation_event(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=StateOperationEventRecord(
            event_id="event-1",
            operation_id=test_case.expected_operation_id,
            action="start",
            status=StateOperationStatus.RUNNING,
            message="started",
        ),
    )
    postgres_state_backend.create_reconcile_event(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=ReconcileEventRecord(
            event_id="event-2",
            action=ReconcileAction.REPORT,
            status=StateOperationStatus.SUCCEEDED,
            message="clean",
        ),
    )

    assert postgres_state_backend.get_state_operation(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        operation_id=test_case.expected_operation_id,
    ) == StateOperationRecord(
        operation_id=test_case.expected_operation_id,
        operation_type=StateOperationType.PROMOTE,
        status=StateOperationStatus.RUNNING,
        virtual_environment_name=test_case.expected_virtual_environment_name,
    )
    assert fetch_all(
        postgres_state_connection,
        "SELECT action, status, message FROM "
        f"{qualified_name(schema=postgres_state_schema, table='state_operation_events')} "
        f"WHERE operation_id = '{test_case.expected_operation_id}'",
    ) == [("start", "running", "started")]
    assert fetch_all(
        postgres_state_connection,
        "SELECT action, status, message FROM "
        f"{qualified_name(schema=postgres_state_schema, table='reconcile_events')} "
        "WHERE event_id = 'event-2'",
    ) == [("report", "succeeded", "clean")]


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
    ids=lambda case: case.description,
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
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        future_expiry: datetime = datetime.now() + timedelta(hours=1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures: list[Future[bool]] = [
                executor.submit(
                    postgres_state_backend.acquire_lock,
                    connection=postgres_state_connection,
                    schema=postgres_state_schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.first_owner,
                    expires_at=future_expiry,
                ),
                executor.submit(
                    postgres_state_backend.acquire_lock,
                    connection=second_connection,
                    schema=postgres_state_schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.second_owner,
                    expires_at=future_expiry,
                ),
            ]
        results: list[bool] = [future.result() for future in futures]

        assert sum(results) == test_case.expected_success_count
        active_locks: tuple[StateLockRecord, ...] = postgres_state_backend.list_active_locks(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
        )
        assert len(active_locks) == test_case.expected_active_lock_count
        assert active_locks[0].owner_id in {test_case.first_owner, test_case.second_owner}
    finally:
        postgres_state_backend.close(second_connection)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresConditionalVirtualRefPublishTestCase(
            description="postgres stale owner cannot publish refs but current owner can",
            expected_stale_publish=False,
            expected_owned_publish=True,
            expected_model_version_hash="version-1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lease_ownership_changes_when_publishing_postgres_refs_then_publish_is_fenced(
    test_case: PostgresConditionalVirtualRefPublishTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="0.0.test",
    )
    lock_key: str = "model-version:warehouse:orders:version-1"
    expires_at: datetime = datetime.now() + timedelta(hours=1)
    assert postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=lock_key,
        owner_id="owner-a",
        expires_at=expires_at,
    )
    stale_lease: StateLockLease = StateLockLease(
        lock_key=lock_key,
        owner_id="owner-a",
        expires_at=expires_at,
    )
    assert postgres_state_backend.release_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=lock_key,
        owner_id="owner-a",
    )
    assert postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=lock_key,
        owner_id="owner-b",
        expires_at=expires_at,
    )
    owned_lease: StateLockLease = StateLockLease(
        lock_key=lock_key,
        owner_id="owner-b",
        expires_at=expires_at,
    )
    record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name="dev",
        status=VirtualEnvironmentStatus.ACTIVE,
    )
    refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = (
        VirtualEnvironmentNodeRefRecord(
            virtual_environment_name="dev",
            node_type="model",
            node_name="orders",
            version_hash=test_case.expected_model_version_hash,
        ),
    )

    stale_published: bool = postgres_state_backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=record,
        refs_by_node_type={"model": refs},
        leases=(stale_lease,),
    )
    assert stale_published is test_case.expected_stale_publish
    assert (
        postgres_state_backend.get_virtual_environment(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
        )
        is None
    )

    owned_published: bool = postgres_state_backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=record,
        refs_by_node_type={"model": refs},
        leases=(owned_lease,),
    )
    assert owned_published is test_case.expected_owned_publish
    assert (
        postgres_state_backend.get_virtual_environment_node_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
            node_type="model",
        )
        == refs
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresAtomicFinalizedVirtualPublishTestCase(
            description="postgres checkpoint failure rolls back finalized publication",
            checkpoint_id="checkpoint-atomic",
            expected_error_fragment="injected checkpoint failure",
            expected_checkpoint_count_after_failure=0,
            expected_checkpoint_count_after_success=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_failure_when_conditionally_publishing_postgres_then_all_rows_roll_back(
    test_case: PostgresAtomicFinalizedVirtualPublishTestCase,
    postgres_state_backend: PostgresStateBackend,
    postgres_state_connection: Any,
    postgres_state_schema: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres_state_backend.initialize(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        sqlbuild_version="0.0.test",
    )
    lock_key: str = "model-version:warehouse:orders:version-1"
    expires_at: datetime = datetime.now() + timedelta(hours=1)
    assert postgres_state_backend.acquire_lock(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        lock_key=lock_key,
        owner_id="owner",
        expires_at=expires_at,
    )
    lease: StateLockLease = StateLockLease(
        lock_key=lock_key,
        owner_id="owner",
        expires_at=expires_at,
    )
    record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name="dev",
        status=VirtualEnvironmentStatus.FINALIZED,
    )
    refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = (
        VirtualEnvironmentNodeRefRecord(
            virtual_environment_name="dev",
            node_type="model",
            node_name="orders",
            version_hash="version-1",
        ),
    )
    checkpoint: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
        checkpoint_id=test_case.checkpoint_id,
        virtual_environment_name="dev",
    )
    checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (
        VirtualEnvironmentCheckpointModelRefRecord(
            checkpoint_id=test_case.checkpoint_id,
            model_name="orders",
            version_hash="version-1",
        ),
    )
    original_insert: Callable[..., None] = (
        postgres_state_backend._insert_virtual_environment_checkpoint_rows
    )

    def _insert_then_fail(**kwargs: Any) -> None:
        original_insert(**kwargs)
        raise RuntimeError(test_case.expected_error_fragment)

    monkeypatch.setattr(
        postgres_state_backend,
        "_insert_virtual_environment_checkpoint_rows",
        _insert_then_fail,
    )
    with pytest.raises(RuntimeError, match=test_case.expected_error_fragment):
        postgres_state_backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            record=record,
            refs_by_node_type={"model": refs},
            leases=(lease,),
            checkpoint=checkpoint,
            checkpoint_refs=checkpoint_refs,
        )
    assert (
        postgres_state_backend.get_virtual_environment(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
        )
        is None
    )
    assert (
        postgres_state_backend.get_virtual_environment_node_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
            node_type="model",
        )
        == ()
    )
    assert (
        len(
            postgres_state_backend.list_virtual_environment_checkpoints(
                connection=postgres_state_connection,
                schema=postgres_state_schema,
                virtual_environment_name="dev",
            )
        )
        == test_case.expected_checkpoint_count_after_failure
    )

    monkeypatch.setattr(
        postgres_state_backend,
        "_insert_virtual_environment_checkpoint_rows",
        original_insert,
    )
    assert postgres_state_backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        connection=postgres_state_connection,
        schema=postgres_state_schema,
        record=record,
        refs_by_node_type={"model": refs},
        leases=(lease,),
        checkpoint=checkpoint,
        checkpoint_refs=checkpoint_refs,
    )
    checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
        postgres_state_backend.list_virtual_environment_checkpoints(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            virtual_environment_name="dev",
        )
    )
    assert len(checkpoints) == test_case.expected_checkpoint_count_after_success
    assert (
        postgres_state_backend.get_virtual_environment_checkpoint_model_refs(
            connection=postgres_state_connection,
            schema=postgres_state_schema,
            checkpoint_id=test_case.checkpoint_id,
        )
        == checkpoint_refs
    )
