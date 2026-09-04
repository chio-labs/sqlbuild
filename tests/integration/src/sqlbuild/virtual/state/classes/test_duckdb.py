from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.commands._helpers.freshness.state import _direct_record_from_virtual_record
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord as DirectSourceFreshnessRecord,
)
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
from sqlbuild.virtual.planner._helpers.run_despite_unchanged import (
    _direct_source_freshness_result,
)
from sqlbuild.virtual.state.constants import (
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_TABLE_INDEXES,
    STATE_TABLES,
)
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
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
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
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
from tests.integration.src.sqlbuild.virtual.state.classes._test_types import (
    AtomicFinalizedVirtualPublishTestCase,
    ConditionalPublicationPayloadContractTestCase,
    ConditionalVirtualRefPublishTestCase,
    DuckDbStateBackendAtomicRefUpdateTestCase,
    DuckDbStateBackendColumnValidationTestCase,
    DuckDbStateBackendConcurrentLockTestCase,
    DuckDbStateBackendCoreRecordsTestCase,
    DuckDbStateBackendErrorTestCase,
    DuckDbStateBackendEventTestCase,
    DuckDbStateBackendIdempotencyTestCase,
    DuckDbStateBackendIndexValidationTestCase,
    DuckDbStateBackendLifecycleTestCase,
    DuckDbStateBackendLockTestCase,
    DuckDbStateBackendNodeResultTestCase,
    DuckDbStateBackendOperationEventTestCase,
    DuckDbStateBackendPythonNodeIdentityTestCase,
    DuckDbStateBackendRollbackTestCase,
    DuckDbStateBackendSeedRefTestCase,
    DuckDbStateBackendSourceFreshnessTestCase,
    DuckDbStateBackendTableCreationTestCase,
    DuckDbStateBackendTransactionRollbackTestCase,
    DuckDbStateBackendValidationTestCase,
    MicrobatchStateRoundTripTestCase,
)
from tests.integration.src.sqlbuild.virtual.state.classes.helpers import (
    ACTIVE_CHECKPOINT_PAYLOAD,
    ACTIVE_PAYLOAD,
    CHECKPOINT_DUPLICATE_PAYLOAD,
    CHECKPOINT_ENVIRONMENT_PAYLOAD,
    CHECKPOINT_ID_PAYLOAD,
    DETACHED_CHECKPOINT_PAYLOAD,
    FAILED_CHECKPOINT_PAYLOAD,
    FINALIZING_CHECKPOINT_PAYLOAD,
    FUNCTION_OMISSION_PAYLOAD,
    MISSING_CHECKPOINT_PAYLOAD,
    MODEL_VERSION_PAYLOAD,
    PUBLISHED_DUPLICATE_PAYLOAD,
    REF_ENVIRONMENT_PAYLOAD,
    REF_NODE_TYPE_PAYLOAD,
    SEED_EXTRA_PAYLOAD,
    VALID_PAYLOAD,
    fetch_all,
    open_duckdb_state_backend,
)

EXPECTED_STATE_INDEX_NAMES: list[str] = []
for state_indexes in STATE_TABLE_INDEXES.values():
    for state_index_name in state_indexes:
        EXPECTED_STATE_INDEX_NAMES.append(state_index_name)
EXPECTED_STATE_INDEX_NAMES.sort()


@pytest.mark.parametrize(
    "test_case",
    [
        ConditionalPublicationPayloadContractTestCase(
            description="duckdb exact finalized payload succeeds",
            payload=VALID_PAYLOAD,
            expected_valid=True,
        ),
        ConditionalPublicationPayloadContractTestCase(
            description="duckdb active payload without checkpoint succeeds",
            payload=ACTIVE_PAYLOAD,
            expected_valid=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_conditional_payload_when_duckdb_publishes_then_contract_succeeds(
    test_case: ConditionalPublicationPayloadContractTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    backend.initialize(connection=connection, schema="sqb_state", sqlbuild_version="test")
    assert (
        backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=connection,
            schema="sqb_state",
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
        ConditionalPublicationPayloadContractTestCase(
            "duckdb finalized requires checkpoint",
            MISSING_CHECKPOINT_PAYLOAD,
            False,
            "requires a checkpoint",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb active forbids complete checkpoint payload",
            ACTIVE_CHECKPOINT_PAYLOAD,
            False,
            "requires finalized virtual environment status",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb finalizing forbids complete checkpoint payload",
            FINALIZING_CHECKPOINT_PAYLOAD,
            False,
            "requires finalized virtual environment status",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb detached forbids complete checkpoint payload",
            DETACHED_CHECKPOINT_PAYLOAD,
            False,
            "requires finalized virtual environment status",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb failed forbids complete checkpoint payload",
            FAILED_CHECKPOINT_PAYLOAD,
            False,
            "requires finalized virtual environment status",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb checkpoint environment matches",
            CHECKPOINT_ENVIRONMENT_PAYLOAD,
            False,
            "match the published environment",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb checkpoint ids match", CHECKPOINT_ID_PAYLOAD, False, "checkpoint_id must match"
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb model refs correspond",
            MODEL_VERSION_PAYLOAD,
            False,
            "model refs must exactly match",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb function refs have no omissions",
            FUNCTION_OMISSION_PAYLOAD,
            False,
            "function refs must exactly match",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb seed refs have no extras",
            SEED_EXTRA_PAYLOAD,
            False,
            "seed refs must exactly match",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb checkpoint refs have no duplicates",
            CHECKPOINT_DUPLICATE_PAYLOAD,
            False,
            "duplicate identities",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb current refs have no duplicates",
            PUBLISHED_DUPLICATE_PAYLOAD,
            False,
            "duplicate identities",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb ref environment matches",
            REF_ENVIRONMENT_PAYLOAD,
            False,
            "virtual_environment_name",
        ),
        ConditionalPublicationPayloadContractTestCase(
            "duckdb ref group matches node type",
            REF_NODE_TYPE_PAYLOAD,
            False,
            "node_type must match",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_conditional_payload_when_duckdb_publishes_then_contract_rejects_before_write(
    test_case: ConditionalPublicationPayloadContractTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    backend.initialize(connection=connection, schema="sqb_state", sqlbuild_version="test")
    with pytest.raises(StateBackendConfigError, match=test_case.expected_error_fragment or ""):
        backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=connection,
            schema="sqb_state",
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
        backend.get_virtual_environment(
            connection=connection,
            schema="sqb_state",
            virtual_environment_name=test_case.payload.record.virtual_environment_name,
        )
        is None
    )


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchStateRoundTripTestCase(
            description="duckdb events are idempotent and preserve concurrent timestamps",
            expected_event_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_microbatch_event_when_appending_then_scope_history_round_trips(
    test_case: MicrobatchStateRoundTripTestCase, tmp_path: Path
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    scope: MicrobatchScope = MicrobatchScope(
        scope_kind="virtual_physical",
        scope_key="duckdb:state:orders:F2:main.orders__F2",
        model_name="orders",
        target_database=None,
        target_schema="main",
        target_name="orders__F2",
        physical_generation_id="F2:main.orders__F2",
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
    try:
        backend.initialize(connection=connection, schema="sqlbuild_state", sqlbuild_version="test")
        backend.append_microbatch_event(connection=connection, schema="sqlbuild_state", event=event)
        second_event: MicrobatchEvent = replace(event, event_id="event-2")
        backend.append_microbatch_event(
            connection=connection, schema="sqlbuild_state", event=second_event
        )
        backend.append_microbatch_event(connection=connection, schema="sqlbuild_state", event=event)

        history: tuple[MicrobatchEvent, ...] = backend.read_microbatch_scope_history(
            connection=connection, schema="sqlbuild_state", scope=scope
        )
        retention_history: tuple[MicrobatchEvent, ...] = backend.read_microbatch_retention_history(
            connection=connection, schema="sqlbuild_state"
        )
        model_history: tuple[MicrobatchEvent, ...] = backend.read_microbatch_model_history(
            connection=connection, schema="sqlbuild_state", scope=scope
        )

        assert len(history) == test_case.expected_event_count
        assert history == (event, second_event)
        assert retention_history == history
        assert model_history == history
    finally:
        backend.close(connection)


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
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_running_lifecycle_then_state_tables_are_managed(
    test_case: DuckDbStateBackendLifecycleTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        version_rows: list[tuple[object, ...]] = fetch_all(
            connection,
            f"SELECT schema_version, sqlbuild_version FROM {test_case.schema}.state_versions",
        )
        assert version_rows == [(test_case.expected_schema_version, test_case.sqlbuild_version)]
        assert backend.inspect_schema(connection=connection, schema=test_case.schema).valid

        backup_id: str = backend.create_backup(connection=connection, schema=test_case.schema)
        assert backup_id
        backup_schemas: list[tuple[object, ...]] = fetch_all(
            connection,
            "SELECT schema_name FROM information_schema.schemata "
            f"WHERE schema_name = '{test_case.expected_backup_prefix}{backup_id}'",
        )
        assert backup_schemas == [(f"{test_case.expected_backup_prefix}{backup_id}",)]

        connection.execute(f"DELETE FROM {test_case.schema}.state_versions")
        assert fetch_all(connection, f"SELECT * FROM {test_case.schema}.state_versions") == []

        rolled_back_backup_id: str = backend.rollback(
            connection=connection, schema=test_case.schema
        )
        assert rolled_back_backup_id == backup_id
        assert fetch_all(
            connection,
            f"SELECT schema_version, sqlbuild_version FROM {test_case.schema}.state_versions",
        ) == [(test_case.expected_schema_version, test_case.sqlbuild_version)]

        backend.reset(connection=connection, schema=test_case.schema)
        validation_after_reset: StateSchemaValidationResult = backend.inspect_schema(
            connection=connection,
            schema=test_case.schema,
        )
        assert not validation_after_reset.valid
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendNodeResultTestCase(
            description="stores and reads VDE node result history by environment",
            schema="sqlbuild_state",
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
def test_given_duckdb_node_results_when_reading_then_scopes_by_environment_and_status(
    test_case: DuckDbStateBackendNodeResultTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
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
        backend.insert_node_result(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
            record=first_record,
        )
        backend.insert_node_result(
            connection=connection,
            schema=test_case.schema,
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
        backend.insert_node_result(
            connection=connection,
            schema=test_case.schema,
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
        backend.insert_node_result(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.isolated_virtual_environment_name,
            record=first_record,
        )
        backend.insert_node_result(
            connection=connection,
            schema=test_case.schema,
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
        backup_id: str = backend.create_backup(connection=connection, schema=test_case.schema)
        connection.execute(f"DELETE FROM {test_case.schema}.node_results")
        backend.rollback(connection=connection, schema=test_case.schema, backup_id=backup_id)

        latest_success: tuple[NodeResultEnvelope, ...] = backend.read_node_results(
            connection=connection,
            schema=test_case.schema,
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
        explicit_failed: tuple[NodeResultEnvelope, ...] = backend.read_node_results(
            connection=connection,
            schema=test_case.schema,
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
        isolated_results: tuple[NodeResultEnvelope, ...] = backend.read_node_results(
            connection=connection,
            schema=test_case.schema,
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
        history_results: tuple[NodeResultEnvelope, ...] = backend.read_node_results(
            connection=connection,
            schema=test_case.schema,
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
        target_isolated_results: tuple[NodeResultEnvelope, ...] = backend.read_node_results(
            connection=connection,
            schema=test_case.schema,
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
        rollback_rows: list[tuple[object, ...]] = fetch_all(
            connection,
            f"SELECT COUNT(*) FROM {test_case.schema}.node_results",
        )

        assert latest_success[0].payload == test_case.expected_latest_payload
        assert explicit_failed[0].status == test_case.expected_failed_status
        assert len(isolated_results) == 1
        assert len(history_results) == test_case.expected_history_count
        assert target_isolated_results[0].payload == test_case.expected_target_isolated_payload
        assert rollback_rows == [(test_case.expected_rollback_row_count,)]
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendValidationTestCase(
            description="reports invalid manually-created state schema",
            schema="broken_state",
            expected_issue_count=24,
        )
    ],
    ids=lambda case: case.description,
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

        result: StateSchemaValidationResult = backend.inspect_schema(
            connection=connection,
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
            expected_index_names=tuple(EXPECTED_STATE_INDEX_NAMES),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backups_when_rolling_back_explicit_id_then_restores_backup(
    test_case: DuckDbStateBackendRollbackTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        first_backup_id: str = backend.create_backup(connection=connection, schema=test_case.schema)
        backend.initialize(
            connection=connection, schema=test_case.schema, sqlbuild_version="0.0.after"
        )
        backend.create_backup(connection=connection, schema=test_case.schema)

        backend.rollback(
            connection=connection,
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
    ids=lambda case: case.description,
)
def test_given_duckdb_state_without_backup_when_rolling_back_then_blocks_cleanly(
    test_case: DuckDbStateBackendErrorTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection, schema=test_case.schema, sqlbuild_version="0.0.test"
        )
        with pytest.raises(test_case.expected_error_type) as exc_info:
            backend.rollback(connection=connection, schema=test_case.schema)

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
    ids=lambda case: case.description,
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
            backend.create_backup(connection=connection, schema=test_case.schema)

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
    ids=lambda case: case.description,
)
def test_given_duckdb_state_lifecycle_when_events_are_recorded_then_backup_contains_event_table(
    test_case: DuckDbStateBackendEventTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backup_id: str = backend.create_backup(connection=connection, schema=test_case.schema)
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
        backend.rollback(connection=connection, schema=test_case.schema, backup_id=backup_id)

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
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_initializing_twice_then_current_version_row_is_idempotent(
    test_case: DuckDbStateBackendIdempotencyTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.first_sqlbuild_version,
        )
        backend.initialize(
            connection=connection,
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
            expected_index_names=tuple(EXPECTED_STATE_INDEX_NAMES),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_initializing_then_creates_all_state_tables(
    test_case: DuckDbStateBackendTableCreationTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
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
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_upserting_core_records_then_round_trips_state(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        assert (
            backend.get_model_version(
                connection=connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            is None
        )
        assert (
            backend.get_physical_relation(
                connection=connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            is None
        )
        assert (
            backend.get_virtual_environment(
                connection=connection,
                schema=test_case.schema,
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
        backend.upsert_model_version(
            connection=connection, schema=test_case.schema, record=model_record
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
        backend.upsert_physical_relation(
            connection=connection, schema=test_case.schema, record=relation_record
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
        backend.upsert_physical_relation(
            connection=connection, schema=test_case.schema, record=replaced_relation_record
        )
        ancestry_record: PhysicalRelationAncestryRecord = PhysicalRelationAncestryRecord(
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            parent_model_name=test_case.expected_model_name,
            parent_version_hash="parent123",
            seed_strategy="copy",
        )
        backend.upsert_physical_relation_ancestry(
            connection=connection, schema=test_case.schema, record=ancestry_record
        )
        virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
            virtual_environment_name=test_case.expected_virtual_environment_name,
            status=VirtualEnvironmentStatus.FINALIZED,
            baseline_virtual_environment_name=None,
        )
        backend.upsert_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            record=virtual_environment_record,
        )
        backend.replace_virtual_environment_model_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
            refs=(
                VirtualEnvironmentModelRefRecord(
                    virtual_environment_name=test_case.expected_virtual_environment_name,
                    model_name=test_case.expected_model_name,
                    version_hash=test_case.expected_version_hash,
                ),
            ),
        )
        backend.replace_virtual_environment_seed_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
            refs=(
                VirtualEnvironmentSeedRefRecord(
                    virtual_environment_name=test_case.expected_virtual_environment_name,
                    seed_name=test_case.expected_model_name,
                    version_hash="seed123",
                ),
            ),
        )
        backend.upsert_virtual_environment_python_node_ref(
            connection=connection,
            schema=test_case.schema,
            ref=VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=test_case.expected_virtual_environment_name,
                node_type="task",
                node_name=test_case.expected_model_name,
                version_hash="task123",
            ),
        )

        assert (
            backend.get_model_version(
                connection=connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == model_record
        )
        assert (
            backend.get_physical_relation(
                connection=connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == replaced_relation_record
        )
        assert (
            backend.get_physical_relation_ancestry(
                connection=connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == ancestry_record
        )
        assert (
            backend.get_virtual_environment(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            )
            == virtual_environment_record
        )
        refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            )
        )
        assert len(refs) == test_case.expected_ref_count
        assert refs[0].model_name == test_case.expected_model_name
        assert refs[0].version_hash == test_case.expected_version_hash
        backend.replace_virtual_environment_model_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
            refs=(),
        )
        seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
            backend.get_virtual_environment_seed_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            )
        )
        assert seed_refs == (
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=test_case.expected_virtual_environment_name,
                seed_name=test_case.expected_model_name,
                version_hash="seed123",
            ),
        )
        python_node_refs: tuple[VirtualEnvironmentPythonNodeRefRecord, ...] = (
            backend.get_virtual_environment_python_node_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            )
        )
        assert python_node_refs == (
            VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=test_case.expected_virtual_environment_name,
                node_type="task",
                node_name=test_case.expected_model_name,
                version_hash="task123",
            ),
        )
        replaced_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            )
        )
        assert len(replaced_refs) == test_case.expected_ref_count_after_replace
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendAtomicRefUpdateTestCase(
            description="rolls back VDE status and all ref groups when atomic replacement fails",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            model_name="orders",
            seed_name="countries",
            expected_original_model_hash="model-old",
            expected_original_seed_hash="seed-old",
            expected_updated_model_hash="model-new",
            expected_updated_seed_hash="seed-new",
            expected_duplicate_seed_hash="seed-duplicate",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_atomic_vde_ref_update_fails_then_rolls_back_all_groups(
    test_case: DuckDbStateBackendAtomicRefUpdateTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backend.upsert_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                status=VirtualEnvironmentStatus.FINALIZED,
            ),
        )
        backend.replace_virtual_environment_model_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
            refs=(
                VirtualEnvironmentModelRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    model_name=test_case.model_name,
                    version_hash=test_case.expected_original_model_hash,
                ),
            ),
        )
        backend.replace_virtual_environment_seed_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
            refs=(
                VirtualEnvironmentSeedRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    seed_name=test_case.seed_name,
                    version_hash=test_case.expected_original_seed_hash,
                ),
            ),
        )

        with pytest.raises(StateBackendConfigError):
            backend.upsert_virtual_environment_and_replace_node_ref_groups(
                connection=connection,
                schema=test_case.schema,
                record=VirtualEnvironmentRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    status=VirtualEnvironmentStatus.ACTIVE,
                ),
                refs_by_node_type={
                    "model": (
                        VirtualEnvironmentNodeRefRecord(
                            virtual_environment_name=test_case.virtual_environment_name,
                            node_type="model",
                            node_name=test_case.model_name,
                            version_hash=test_case.expected_updated_model_hash,
                        ),
                    ),
                    "seed": (
                        VirtualEnvironmentNodeRefRecord(
                            virtual_environment_name=test_case.virtual_environment_name,
                            node_type="seed",
                            node_name=test_case.seed_name,
                            version_hash=test_case.expected_updated_seed_hash,
                        ),
                        VirtualEnvironmentNodeRefRecord(
                            virtual_environment_name=test_case.virtual_environment_name,
                            node_type="seed",
                            node_name=test_case.seed_name,
                            version_hash=test_case.expected_duplicate_seed_hash,
                        ),
                    ),
                },
            )

        assert backend.get_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
        ) == VirtualEnvironmentRecord(
            virtual_environment_name=test_case.virtual_environment_name,
            status=VirtualEnvironmentStatus.FINALIZED,
        )
        assert backend.get_virtual_environment_model_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
        ) == (
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                model_name=test_case.model_name,
                version_hash=test_case.expected_original_model_hash,
            ),
        )
        assert backend.get_virtual_environment_seed_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
        ) == (
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                seed_name=test_case.seed_name,
                version_hash=test_case.expected_original_seed_hash,
            ),
        )
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        ConditionalVirtualRefPublishTestCase(
            description="stale owner cannot publish refs but current owner can",
            expected_stale_publish=False,
            expected_owned_publish=True,
            expected_model_version_hash="version-1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lease_ownership_changes_when_publishing_duckdb_refs_then_publish_is_fenced(
    test_case: ConditionalVirtualRefPublishTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    schema: str = "sqlbuild_state"
    lock_key: str = "model-version:warehouse:orders:version-1"
    expires_at: datetime = datetime.now() + timedelta(hours=1)
    backend.initialize(connection=connection, schema=schema, sqlbuild_version="0.0.test")
    assert backend.acquire_lock(
        connection=connection,
        schema=schema,
        lock_key=lock_key,
        owner_id="owner-a",
        expires_at=expires_at,
    )
    stale_lease: StateLockLease = StateLockLease(
        lock_key=lock_key,
        owner_id="owner-a",
        expires_at=expires_at,
    )
    assert backend.release_lock(
        connection=connection,
        schema=schema,
        lock_key=lock_key,
        owner_id="owner-a",
    )
    assert backend.acquire_lock(
        connection=connection,
        schema=schema,
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

    stale_published: bool = (
        backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=connection,
            schema=schema,
            record=record,
            refs_by_node_type={"model": refs},
            leases=(stale_lease,),
        )
    )
    assert stale_published is test_case.expected_stale_publish
    assert (
        backend.get_virtual_environment(
            connection=connection,
            schema=schema,
            virtual_environment_name="dev",
        )
        is None
    )

    owned_published: bool = (
        backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=connection,
            schema=schema,
            record=record,
            refs_by_node_type={"model": refs},
            leases=(owned_lease,),
        )
    )
    assert owned_published is test_case.expected_owned_publish
    assert (
        backend.get_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name="dev",
            node_type="model",
        )
        == refs
    )
    backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        AtomicFinalizedVirtualPublishTestCase(
            description="duckdb checkpoint failure rolls back finalized publication",
            checkpoint_id="checkpoint-atomic",
            expected_error_fragment="injected checkpoint failure",
            expected_checkpoint_count_after_failure=0,
            expected_checkpoint_count_after_success=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_failure_when_conditionally_publishing_duckdb_then_all_rows_roll_back(
    test_case: AtomicFinalizedVirtualPublishTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    schema: str = "sqlbuild_state"
    lock_key: str = "model-version:warehouse:orders:version-1"
    expires_at: datetime = datetime.now() + timedelta(hours=1)
    backend.initialize(connection=connection, schema=schema, sqlbuild_version="0.0.test")
    assert backend.acquire_lock(
        connection=connection,
        schema=schema,
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
    original_insert: Callable[..., None] = backend._insert_virtual_environment_checkpoint_rows

    def _insert_then_fail(**kwargs: Any) -> None:
        original_insert(**kwargs)
        raise RuntimeError(test_case.expected_error_fragment)

    monkeypatch.setattr(backend, "_insert_virtual_environment_checkpoint_rows", _insert_then_fail)
    with pytest.raises(RuntimeError, match=test_case.expected_error_fragment):
        backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
            connection=connection,
            schema=schema,
            record=record,
            refs_by_node_type={"model": refs},
            leases=(lease,),
            checkpoint=checkpoint,
            checkpoint_refs=checkpoint_refs,
        )
    assert (
        backend.get_virtual_environment(
            connection=connection,
            schema=schema,
            virtual_environment_name="dev",
        )
        is None
    )
    assert (
        backend.get_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name="dev",
            node_type="model",
        )
        == ()
    )
    assert (
        len(
            backend.list_virtual_environment_checkpoints(
                connection=connection,
                schema=schema,
                virtual_environment_name="dev",
            )
        )
        == test_case.expected_checkpoint_count_after_failure
    )

    monkeypatch.setattr(backend, "_insert_virtual_environment_checkpoint_rows", original_insert)
    assert backend.upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        connection=connection,
        schema=schema,
        record=record,
        refs_by_node_type={"model": refs},
        leases=(lease,),
        checkpoint=checkpoint,
        checkpoint_refs=checkpoint_refs,
    )
    checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
        backend.list_virtual_environment_checkpoints(
            connection=connection,
            schema=schema,
            virtual_environment_name="dev",
        )
    )
    assert len(checkpoints) == test_case.expected_checkpoint_count_after_success
    assert (
        backend.get_virtual_environment_checkpoint_model_refs(
            connection=connection,
            schema=schema,
            checkpoint_id=test_case.checkpoint_id,
        )
        == checkpoint_refs
    )
    backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendSourceFreshnessTestCase(
            description="persists and replaces source freshness observations",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            expected_source_names=("raw.customers", "raw.orders"),
            expected_source_names_after_replace=("raw.orders",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_replacing_source_freshness_then_round_trips_latest_records(
    test_case: DuckDbStateBackendSourceFreshnessTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        connection.execute("SET TimeZone = 'Asia/Singapore'")
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backend.upsert_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=test_case.virtual_environment_name,
                status=VirtualEnvironmentStatus.ACTIVE,
            ),
        )
        first_observed_at: datetime = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        second_observed_at: datetime = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
        backend.replace_virtual_environment_source_freshness(
            connection=connection,
            schema=test_case.schema,
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
            backend.get_virtual_environment_source_freshness(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.virtual_environment_name,
            )
        )
        assert tuple(record.source_name for record in records) == test_case.expected_source_names

        backend.replace_virtual_environment_source_freshness(
            connection=connection,
            schema=test_case.schema,
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
            backend.get_virtual_environment_source_freshness(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.virtual_environment_name,
            )
        )
        assert tuple(record.source_name for record in replaced_records) == (
            test_case.expected_source_names_after_replace
        )
        assert replaced_records[0].data_version == "2"
        assert replaced_records[0].data_version_hash == "hash-3"
        assert replaced_records[0].observed_at == second_observed_at
        stored_observed_at: datetime = connection.execute(
            f'SELECT observed_at FROM "{test_case.schema}"."{SOURCE_FRESHNESS_OBSERVATION_TABLE}"'
        ).fetchone()[0]
        assert stored_observed_at == second_observed_at.replace(tzinfo=None)
        planning_result: DirectSourceFreshnessPlanningResult = _direct_source_freshness_result(
            replaced_records
        )
        assert planning_result.observed_records[0].observed_at == second_observed_at
        direct_record: DirectSourceFreshnessRecord = _direct_record_from_virtual_record(
            replaced_records[0]
        )
        assert direct_record.observed_at == second_observed_at

        backend.delete_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
        assert (
            backend.get_virtual_environment_source_freshness(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.virtual_environment_name,
            )
            == ()
        )
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendSeedRefTestCase(
            description="persists seed versions and replaces seed refs",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            virtual_environment_name="dev",
            seed_name="country_codes",
            version_hash="seed123",
            identity_metadata_hash="meta123",
            identity_metadata_json_b64="e30=",
            replacement_version_hash="seed456",
            expected_ref_count_after_replace=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_replacing_seed_refs_then_round_trips_records(
    test_case: DuckDbStateBackendSeedRefTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        seed_version: SeedVersionRecord = SeedVersionRecord(
            seed_name=test_case.seed_name,
            version_hash=test_case.version_hash,
            identity_metadata_hash=test_case.identity_metadata_hash,
            identity_metadata_json_b64=test_case.identity_metadata_json_b64,
            status=ModelVersionStatus.READY,
        )
        backend.upsert_seed_version(
            connection=connection, schema=test_case.schema, record=seed_version
        )
        backend.replace_virtual_environment_seed_refs(
            connection=connection,
            schema=test_case.schema,
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
            backend.get_seed_version(
                connection=connection,
                schema=test_case.schema,
                seed_name=test_case.seed_name,
                version_hash=test_case.version_hash,
            )
            == seed_version
        )
        refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
            backend.get_virtual_environment_seed_refs(
                connection=connection,
                schema=test_case.schema,
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

        backend.replace_virtual_environment_seed_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
            refs=(),
        )
        assert (
            len(
                backend.get_virtual_environment_seed_refs(
                    connection=connection,
                    schema=test_case.schema,
                    virtual_environment_name=test_case.virtual_environment_name,
                )
            )
            == test_case.expected_ref_count_after_replace
        )
        backend.replace_virtual_environment_seed_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
            refs=(
                VirtualEnvironmentSeedRefRecord(
                    virtual_environment_name=test_case.virtual_environment_name,
                    seed_name=test_case.seed_name,
                    version_hash=test_case.version_hash,
                ),
            ),
        )
        backend.delete_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.virtual_environment_name,
        )
        assert (
            backend.get_virtual_environment_seed_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.virtual_environment_name,
            )
            == ()
        )

        checkpoint: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
            checkpoint_id="chk_seed",
            virtual_environment_name=test_case.virtual_environment_name,
        )
        backend.create_virtual_environment_checkpoint(
            connection=connection,
            schema=test_case.schema,
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
            backend.get_virtual_environment_checkpoint_seed_refs(
                connection=connection,
                schema=test_case.schema,
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
        backend.delete_virtual_environment_checkpoint(
            connection=connection,
            schema=test_case.schema,
            checkpoint_id=checkpoint.checkpoint_id,
        )
        assert (
            backend.get_virtual_environment_checkpoint_seed_refs(
                connection=connection,
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
        DuckDbStateBackendErrorTestCase(
            description="blocks mismatched source freshness virtual environment",
            schema="sqlbuild_state",
            expected_error_type=Exception,
            expected_message_fragment="must match replacement virtual_environment_name",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_mismatched_duckdb_source_freshness_record_when_replacing_then_blocks_cleanly(
    test_case: DuckDbStateBackendErrorTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection, schema=test_case.schema, sqlbuild_version="0.0.test"
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
            backend.replace_virtual_environment_source_freshness(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name="dev",
                records=(record,),
            )

        assert test_case.expected_message_fragment in str(exc_info.value)
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendErrorTestCase(
            description="blocks duplicate source freshness records",
            schema="sqlbuild_state",
            expected_error_type=Exception,
            expected_message_fragment="Duplicate source freshness record",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_duckdb_source_freshness_records_when_replacing_then_blocks_cleanly(
    test_case: DuckDbStateBackendErrorTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection, schema=test_case.schema, sqlbuild_version="0.0.test"
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
            backend.replace_virtual_environment_source_freshness(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name="dev",
                records=records,
            )

        assert test_case.expected_message_fragment in str(exc_info.value)
    finally:
        backend.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbStateBackendPythonNodeIdentityTestCase(
            description="persists python node versions and separate VDE refs",
            schema="sqlbuild_state",
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
def test_given_duckdb_state_backend_when_upserting_python_node_identity_then_round_trips_refs(
    test_case: DuckDbStateBackendPythonNodeIdentityTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
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

        backend.upsert_python_node_version(
            connection=connection, schema=test_case.schema, record=first_record
        )
        backend.upsert_python_node_version(
            connection=connection, schema=test_case.schema, record=second_record
        )
        backend.upsert_python_node_version(
            connection=connection, schema=test_case.schema, record=orphan_record
        )
        backend.upsert_virtual_environment_python_node_ref(
            connection=connection,
            schema=test_case.schema,
            ref=VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=test_case.first_virtual_environment_name,
                node_type=test_case.node_type,
                node_name=test_case.node_name,
                version_hash=test_case.first_version_hash,
            ),
        )
        backend.upsert_virtual_environment_python_node_ref(
            connection=connection,
            schema=test_case.schema,
            ref=VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=test_case.second_virtual_environment_name,
                node_type=test_case.node_type,
                node_name=test_case.node_name,
                version_hash=test_case.second_version_hash,
            ),
        )

        first_refs: tuple[VirtualEnvironmentPythonNodeRefRecord, ...] = (
            backend.get_virtual_environment_python_node_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.first_virtual_environment_name,
            )
        )
        second_refs: tuple[VirtualEnvironmentPythonNodeRefRecord, ...] = (
            backend.get_virtual_environment_python_node_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.second_virtual_environment_name,
            )
        )

        assert (
            backend.get_python_node_version(
                connection=connection,
                schema=test_case.schema,
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
            backend.count_unreferenced_python_node_versions(
                connection=connection, schema=test_case.schema
            )
            == test_case.expected_pruned_count
        )
        assert (
            backend.prune_unreferenced_python_node_versions(
                connection=connection, schema=test_case.schema
            )
            == test_case.expected_pruned_count
        )
        assert (
            backend.get_python_node_version(
                connection=connection,
                schema=test_case.schema,
                node_type=test_case.node_type,
                node_name=test_case.node_name,
                version_hash=test_case.orphan_version_hash,
            )
            is None
        )
        assert (
            backend.get_python_node_version(
                connection=connection,
                schema=test_case.schema,
                node_type=test_case.node_type,
                node_name=test_case.node_name,
                version_hash=test_case.second_version_hash,
            )
            == second_record
        )
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
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="unused",
            expected_replaced_relation_name="unused",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_upserting_function_records_then_round_trips_state(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        assert (
            backend.get_function_version(
                connection=connection,
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
            definition_text_b64="YW1vdW50ID4gOQ==",
            status=ModelVersionStatus.READY,
        )
        backend.upsert_function_version(
            connection=connection,
            schema=test_case.schema,
            record=function_record,
        )
        assert (
            backend.get_function_version(
                connection=connection,
                schema=test_case.schema,
                function_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == function_record
        )
        backend.replace_virtual_environment_function_refs(
            connection=connection,
            schema=test_case.schema,
            virtual_environment_name=test_case.expected_virtual_environment_name,
            refs=(
                VirtualEnvironmentFunctionRefRecord(
                    virtual_environment_name=test_case.expected_virtual_environment_name,
                    node_type="udf",
                    function_name=test_case.expected_model_name,
                    version_hash=test_case.expected_version_hash,
                ),
            ),
        )
        function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = (
            backend.get_virtual_environment_function_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            )
        )
        assert len(function_refs) == test_case.expected_ref_count
        assert function_refs[0].function_name == test_case.expected_model_name
        checkpoint: VirtualEnvironmentCheckpointRecord = VirtualEnvironmentCheckpointRecord(
            checkpoint_id="chk_function",
            virtual_environment_name=test_case.expected_virtual_environment_name,
        )
        backend.create_virtual_environment_checkpoint(
            connection=connection,
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
                connection=connection,
                schema=test_case.schema,
                checkpoint_id=checkpoint.checkpoint_id,
            )
        )
        assert len(checkpoint_function_refs) == test_case.expected_ref_count
        backend.delete_virtual_environment_checkpoint(
            connection=connection,
            schema=test_case.schema,
            checkpoint_id=checkpoint.checkpoint_id,
        )
        assert (
            backend.get_virtual_environment_checkpoint_function_refs(
                connection=connection,
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
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_managing_locks_then_enforces_active_owner(
    test_case: DuckDbStateBackendLockTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        future_expiry: datetime = datetime.now() + timedelta(hours=1)
        expired_at: datetime = datetime.now() - timedelta(hours=1)

        assert backend.acquire_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
            expires_at=future_expiry,
        )
        assert not backend.acquire_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
            expires_at=future_expiry,
        )
        renewed_expiry: datetime = future_expiry + timedelta(hours=1)
        assert backend.renew_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
            expires_at=renewed_expiry,
        )
        assert not backend.renew_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
            expires_at=renewed_expiry,
        )
        active_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
            schema=test_case.schema,
        )
        assert len(active_locks) == test_case.expected_active_lock_count
        assert active_locks[0].owner_id == test_case.first_owner
        assert not backend.release_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
        )
        assert backend.release_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
        )
        assert backend.list_active_locks(connection=connection, schema=test_case.schema) == ()

        assert backend.acquire_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.first_owner,
            expires_at=expired_at,
        )
        assert backend.acquire_lock(
            connection=connection,
            schema=test_case.schema,
            lock_key=test_case.lock_key,
            owner_id=test_case.second_owner,
            expires_at=future_expiry,
        )
        replacement_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=connection,
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
            description="reports missing node results latest index",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            dropped_index_name="idx_sqb_node_results_latest",
            expected_issue_kind=StateSchemaValidationIssueKind.MISSING_INDEX.value,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_required_index_is_missing_then_validation_reports_it(
    test_case: DuckDbStateBackendIndexValidationTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )

        connection.execute(f"DROP INDEX {test_case.schema}.{test_case.dropped_index_name}")

        validation_result: StateSchemaValidationResult = backend.inspect_schema(
            connection=connection,
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
        DuckDbStateBackendColumnValidationTestCase(
            description="reports missing node results payload column",
            schema="sqlbuild_state",
            sqlbuild_version="0.0.test",
            dropped_table_name="node_results",
            dropped_column_name="payload_json_b64",
            expected_issue_kind=StateSchemaValidationIssueKind.MISSING_COLUMN.value,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_node_results_column_is_missing_then_validation_reports_it(
    test_case: DuckDbStateBackendColumnValidationTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )

        index_name: str
        for index_name in STATE_TABLE_INDEXES[test_case.dropped_table_name]:
            connection.execute(f"DROP INDEX {test_case.schema}.{index_name}")
        connection.execute(
            f"ALTER TABLE {test_case.schema}.{test_case.dropped_table_name} "
            f"DROP COLUMN {test_case.dropped_column_name}"
        )

        validation_result: StateSchemaValidationResult = backend.inspect_schema(
            connection=connection,
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
            virtual_environment_name="dev",
            model_name="fact_orders",
            original_version_hash="abc123",
            duplicate_version_hash="def456",
            expected_ref_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_ref_replace_fails_then_transaction_rolls_back(
    test_case: DuckDbStateBackendTransactionRollbackTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backend.replace_virtual_environment_model_refs(
            connection=connection,
            schema=test_case.schema,
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
            backend.replace_virtual_environment_model_refs(
                connection=connection,
                schema=test_case.schema,
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
            backend.get_virtual_environment_model_refs(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.virtual_environment_name,
            )
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
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_upserting_same_identity_then_created_at_is_preserved(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        model_record: ModelVersionRecord = ModelVersionRecord(
            model_name=test_case.expected_model_name,
            version_hash=test_case.expected_version_hash,
            definition_identity_hash="definition-identity-hash",
            identity_metadata_hash="identity-metadata-hash",
            status=ModelVersionStatus.READY,
        )
        backend.upsert_model_version(
            connection=connection, schema=test_case.schema, record=model_record
        )
        original_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.model_versions "
            f"WHERE model_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]

        backend.upsert_model_version(
            connection=connection, schema=test_case.schema, record=model_record
        )

        replaced_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.model_versions "
            f"WHERE model_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]
        assert (
            backend.get_model_version(
                connection=connection,
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
            expected_virtual_environment_name="dev",
            expected_ref_count=1,
            expected_ref_count_after_replace=0,
            expected_relation_name="fact_orders__v_abc123",
            expected_replaced_relation_name="fact_orders__v_abc123_replaced",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_replacing_rows_then_preserves_created_at(
    test_case: DuckDbStateBackendCoreRecordsTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
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
        backend.upsert_physical_relation(
            connection=connection,
            schema=test_case.schema,
            record=relation_record,
        )
        physical_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.physical_relations "
            "WHERE artifact_type = 'model' "
            f"AND artifact_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]
        backend.upsert_physical_relation(
            connection=connection,
            schema=test_case.schema,
            record=relation_record,
        )
        replaced_physical_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.physical_relations "
            "WHERE artifact_type = 'model' "
            f"AND artifact_name = '{test_case.expected_model_name}' "
            f"AND version_hash = '{test_case.expected_version_hash}'",
        )[0][0]

        virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
            virtual_environment_name=test_case.expected_virtual_environment_name,
            status=VirtualEnvironmentStatus.FINALIZED,
            baseline_virtual_environment_name=None,
        )
        backend.upsert_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            record=virtual_environment_record,
        )
        virtual_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.virtual_environments "
            f"WHERE virtual_environment_name = '{test_case.expected_virtual_environment_name}'",
        )[0][0]
        backend.upsert_virtual_environment(
            connection=connection,
            schema=test_case.schema,
            record=virtual_environment_record,
        )
        replaced_virtual_created_at: datetime = fetch_all(
            connection,
            f"SELECT created_at FROM {test_case.schema}.virtual_environments "
            f"WHERE virtual_environment_name = '{test_case.expected_virtual_environment_name}'",
        )[0][0]

        assert (
            backend.get_physical_relation(
                connection=connection,
                schema=test_case.schema,
                model_name=test_case.expected_model_name,
                version_hash=test_case.expected_version_hash,
            )
            == relation_record
        )
        assert (
            backend.get_virtual_environment(
                connection=connection,
                schema=test_case.schema,
                virtual_environment_name=test_case.expected_virtual_environment_name,
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
            expected_virtual_environment_name="dev",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duckdb_state_backend_when_recording_operation_events_then_they_round_trip(
    test_case: DuckDbStateBackendOperationEventTestCase,
    tmp_path: Path,
) -> None:
    backend, connection = open_duckdb_state_backend(db_path=tmp_path / "state.duckdb")
    try:
        backend.initialize(
            connection=connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        backend.upsert_state_operation(
            connection=connection,
            schema=test_case.schema,
            record=StateOperationRecord(
                operation_id=test_case.expected_operation_id,
                operation_type=StateOperationType.PROMOTE,
                status=StateOperationStatus.RUNNING,
                virtual_environment_name=test_case.expected_virtual_environment_name,
            ),
        )
        backend.create_state_operation_event(
            connection=connection,
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
            connection=connection,
            schema=test_case.schema,
            record=ReconcileEventRecord(
                event_id="event-2",
                action=ReconcileAction.REPORT,
                status=StateOperationStatus.SUCCEEDED,
                message="clean",
            ),
        )

        assert backend.get_state_operation(
            connection=connection,
            schema=test_case.schema,
            operation_id=test_case.expected_operation_id,
        ) == StateOperationRecord(
            operation_id=test_case.expected_operation_id,
            operation_type=StateOperationType.PROMOTE,
            status=StateOperationStatus.RUNNING,
            virtual_environment_name=test_case.expected_virtual_environment_name,
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
    ids=lambda case: case.description,
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
            connection=first_connection,
            schema=test_case.schema,
            sqlbuild_version=test_case.sqlbuild_version,
        )
        future_expiry: datetime = datetime.now() + timedelta(hours=1)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures: list[Future[bool]] = [
                executor.submit(
                    backend.acquire_lock,
                    connection=first_connection,
                    schema=test_case.schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.first_owner,
                    expires_at=future_expiry,
                ),
                executor.submit(
                    second_backend.acquire_lock,
                    connection=second_connection,
                    schema=test_case.schema,
                    lock_key=test_case.lock_key,
                    owner_id=test_case.second_owner,
                    expires_at=future_expiry,
                ),
            ]
        results: list[bool] = [future.result() for future in futures]

        assert sum(results) == test_case.expected_success_count
        active_locks: tuple[StateLockRecord, ...] = backend.list_active_locks(
            connection=first_connection,
            schema=test_case.schema,
        )
        assert len(active_locks) == test_case.expected_active_lock_count
        assert active_locks[0].owner_id in {test_case.first_owner, test_case.second_owner}
    finally:
        backend.close(first_connection)
        second_backend.close(second_connection)
