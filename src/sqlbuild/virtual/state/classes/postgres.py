"""Postgres virtual-state backend."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.observed_connection import ObservedConnection
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.executor.node_results.main.decode_json import decode_node_result_json
from sqlbuild.executor.node_results.main.encode_json import encode_node_result_json
from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import (
    MICROBATCH_COLUMNS,
    MICROBATCH_GENERATION_WILDCARD,
    VIRTUAL_MICROBATCH_SCOPE_KIND,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from sqlbuild.virtual.state._helpers.state_storage.events import backup_id, event_id
from sqlbuild.virtual.state._helpers.state_storage.validation import (
    build_validation_result,
    validate_conditional_virtual_environment_publication,
)
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import (
    CURRENT_STATE_SCHEMA_VERSION,
    FUNCTION_VERSION_TABLE,
    LOCK_TABLE,
    MICROBATCH_EVENT_TABLE,
    MODEL_VERSION_TABLE,
    NODE_RESULTS_TABLE,
    NON_UNIQUE_STATE_INDEXES,
    PHYSICAL_RELATION_ANCESTRY_TABLE,
    PHYSICAL_RELATION_TABLE,
    POSTGRES_INTEGER_TYPES,
    POSTGRES_TEXT_TYPES,
    PYTHON_NODE_VERSION_TABLE,
    RECONCILE_EVENT_TABLE,
    SEED_VERSION_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_BOOLEAN_TRUE,
    STATE_MIGRATION_EVENTS_TABLE,
    STATE_OPERATION_EVENT_TABLE,
    STATE_OPERATION_TABLE,
    STATE_TABLE_COLUMNS,
    STATE_TABLE_INDEXES,
    STATE_TABLES,
    STATE_VERSION_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
    VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
    VIRTUAL_ENVIRONMENT_TABLE,
)
from sqlbuild.virtual.state.exceptions import (
    StateBackendConfigError,
    StateBackupNotFoundError,
    StateSchemaInvalidError,
)
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    ModelVersionRecord,
    PhysicalRelationAncestryRecord,
    PhysicalRelationRecord,
    PythonNodeVersionRecord,
    ReconcileEventRecord,
    SeedVersionRecord,
    SourceFreshnessRecord,
    StateBackupRecord,
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
    VirtualEnvironmentRetentionRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    PhysicalArtifactType,
    StateColumnType,
    StateMigrationAction,
    StateMigrationStatus,
    StateOperationStatus,
    StateOperationType,
    VirtualEnvironmentStatus,
)


class PostgresStateBackend(StateBackend):
    """Postgres implementation for virtual state."""

    def connect(self, config: dict[str, object]) -> Any:
        try:
            import psycopg
        except ImportError as error:
            raise StateBackendConfigError(
                "Postgres state backend requires optional dependency psycopg. "
                "Install with: pip install 'psycopg[binary]' or sqlbuild[postgres]"
            ) from error

        try:
            return ObservedConnection(
                raw_connection=psycopg.connect(
                    host=_optional_str(config.get("host")),
                    port=_optional_int(config.get("port")),
                    user=_optional_str(config.get("user")),
                    password=_optional_str(config.get("password")),
                    dbname=_optional_str(config.get("dbname")),
                    autocommit=True,
                ),
                adapter="postgres",
            )
        except Exception as error:
            raise StateBackendConfigError("Could not connect to Postgres state backend") from error

    def close(self, connection: Any) -> None:
        connection.close()

    def initialize(self, *, connection: Any, schema: str, sqlbuild_version: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS "
                    f"{self._qualified_name(schema=schema, table=STATE_VERSION_TABLE)} ("
                    "schema_version INTEGER NOT NULL, "
                    "sqlbuild_version TEXT NOT NULL, "
                    "updated_at TIMESTAMP NOT NULL"
                    ")"
                )
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS "
                    f"{self._qualified_name(schema=schema, table=STATE_MIGRATION_EVENTS_TABLE)} ("
                    "event_id TEXT NOT NULL, "
                    "action TEXT NOT NULL, "
                    "backup_id TEXT, "
                    "status TEXT NOT NULL, "
                    "message TEXT, "
                    "created_at TIMESTAMP NOT NULL"
                    ")"
                )
                self._create_additional_state_tables(cursor=cursor, schema=schema)
                cursor.execute(
                    f"DELETE FROM {self._qualified_name(schema=schema, table=STATE_VERSION_TABLE)}"
                )
                cursor.execute(
                    f"INSERT INTO {self._qualified_name(schema=schema, table=STATE_VERSION_TABLE)} "
                    "(schema_version, sqlbuild_version, updated_at) "
                    "VALUES (%s, %s, CURRENT_TIMESTAMP)",
                    [CURRENT_STATE_SCHEMA_VERSION, sqlbuild_version],
                )
                self._record_event(
                    cursor=cursor,
                    schema=schema,
                    action=StateMigrationAction.INIT,
                    backup_id_value=None,
                    status=StateMigrationStatus.SUCCESS,
                    message=None,
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def inspect_schema(self, *, connection: Any, schema: str) -> StateSchemaValidationResult:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                [schema],
            )
            tables: set[str] = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s",
                [schema],
            )
            columns_by_table: dict[str, dict[str, str]] = {}
            for row in cursor.fetchall():
                columns_by_table.setdefault(row[0], {})[row[1]] = row[2]
            cursor.execute(
                "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = %s",
                [schema],
            )
            indexes_by_table: dict[str, set[str]] = {}
            for row in cursor.fetchall():
                indexes_by_table.setdefault(row[0], set()).add(row[1])
        return build_validation_result(
            existing_tables=tables,
            columns_by_table=columns_by_table,
            expected_columns=STATE_TABLE_COLUMNS,
            type_matches=self._state_type_matches,
            expected_indexes=STATE_TABLE_INDEXES,
            existing_indexes_by_table=indexes_by_table,
        )

    def create_backup(self, *, connection: Any, schema: str) -> str:
        validation: StateSchemaValidationResult = self.inspect_schema(
            connection=connection, schema=schema
        )
        if not validation.valid:
            raise StateSchemaInvalidError("Cannot backup invalid state schema")
        backup_id_value: str = backup_id()
        backup_schema: str = self._backup_schema_name(
            schema=schema,
            backup_id_value=backup_id_value,
        )
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(f"CREATE SCHEMA {self._quote_identifier(backup_schema)}")
                table_name: str
                for table_name in STATE_TABLES:
                    cursor.execute(
                        "CREATE TABLE "
                        + self._qualified_name(schema=backup_schema, table=table_name)
                        + " AS "
                        f"SELECT * FROM {self._qualified_name(schema=schema, table=table_name)}"
                    )
                self._record_event(
                    cursor=cursor,
                    schema=schema,
                    action=StateMigrationAction.BACKUP,
                    backup_id_value=backup_id_value,
                    status=StateMigrationStatus.SUCCESS,
                    message=None,
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise
        return backup_id_value

    def rollback(self, *, connection: Any, schema: str, backup_id: str | None = None) -> str:
        backup_id_value: str = backup_id or self._latest_backup_id(
            connection=connection, schema=schema
        )
        backup_schema: str = self._backup_schema_name(
            schema=schema,
            backup_id_value=backup_id_value,
        )
        if not self._schema_exists(connection=connection, schema=backup_schema):
            raise StateBackupNotFoundError(f"State backup schema '{backup_schema}' does not exist")
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                table_name: str
                for table_name in STATE_TABLES:
                    cursor.execute(
                        "DROP TABLE IF EXISTS "
                        f"{self._qualified_name(schema=schema, table=table_name)}"
                    )
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
                for table_name in STATE_TABLES:
                    cursor.execute(
                        f"CREATE TABLE {self._qualified_name(schema=schema, table=table_name)} AS "
                        "SELECT * FROM "
                        f"{self._qualified_name(schema=backup_schema, table=table_name)}"
                    )
                self._create_state_indexes(cursor=cursor, schema=schema)
                self._record_event(
                    cursor=cursor,
                    schema=schema,
                    action=StateMigrationAction.ROLLBACK,
                    backup_id_value=backup_id_value,
                    status=StateMigrationStatus.SUCCESS,
                    message=None,
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise
        return backup_id_value

    def reset(self, *, connection: Any, schema: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                table_name: str
                for table_name in STATE_TABLES:
                    cursor.execute(
                        "DROP TABLE IF EXISTS "
                        f"{self._qualified_name(schema=schema, table=table_name)}"
                    )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def upsert_model_version(
        self, *, connection: Any, schema: str, record: ModelVersionRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=MODEL_VERSION_TABLE,
                    where_sql="model_name = %s AND version_hash = %s",
                    params=[record.model_name, record.version_hash],
                )
                cursor.execute(
                    f"DELETE FROM {self._qualified_name(schema=schema, table=MODEL_VERSION_TABLE)} "
                    "WHERE model_name = %s AND version_hash = %s",
                    [record.model_name, record.version_hash],
                )
                cursor.execute(
                    f"INSERT INTO {self._qualified_name(schema=schema, table=MODEL_VERSION_TABLE)} "
                    "(model_name, version_hash, definition_identity_hash, "
                    "identity_metadata_hash, definition_text_b64, identity_metadata_json_b64, "
                    "compiled_sql_b64, status, "
                    "created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
                    "COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.model_name,
                        record.version_hash,
                        record.definition_identity_hash,
                        record.identity_metadata_hash,
                        record.definition_text_b64,
                        record.identity_metadata_json_b64,
                        record.compiled_sql_b64,
                        record.status.value,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_model_version(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT model_name, version_hash, definition_identity_hash, "
                "identity_metadata_hash, definition_text_b64, identity_metadata_json_b64, "
                "compiled_sql_b64, status "
                f"FROM {self._qualified_name(schema=schema, table=MODEL_VERSION_TABLE)} "
                "WHERE model_name = %s AND version_hash = %s",
                [model_name, version_hash],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return ModelVersionRecord(
            model_name=row[0],
            version_hash=row[1],
            definition_identity_hash=row[2],
            identity_metadata_hash=row[3],
            definition_text_b64=row[4],
            identity_metadata_json_b64=row[5],
            compiled_sql_b64=row[6],
            status=ModelVersionStatus(row[7]),
        )

    def upsert_function_version(
        self, *, connection: Any, schema: str, record: FunctionVersionRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=FUNCTION_VERSION_TABLE,
                    where_sql="function_name = %s AND version_hash = %s",
                    params=[record.function_name, record.version_hash],
                )
                cursor.execute(
                    "DELETE FROM "
                    f"{self._qualified_name(schema=schema, table=FUNCTION_VERSION_TABLE)} "
                    "WHERE function_name = %s AND version_hash = %s",
                    [record.function_name, record.version_hash],
                )
                cursor.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema=schema, table=FUNCTION_VERSION_TABLE)} "
                    "(function_name, version_hash, language, returns, arguments_json_b64, "
                    "return_columns_json_b64, packages_json_b64, runtime_version, entry_point, "
                    "body_sql_b64, definition_text_b64, status, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.function_name,
                        record.version_hash,
                        record.language,
                        record.returns,
                        record.arguments_json_b64,
                        record.return_columns_json_b64,
                        record.packages_json_b64,
                        record.runtime_version,
                        record.entry_point,
                        record.body_sql_b64,
                        record.definition_text_b64,
                        record.status.value,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_function_version(
        self, *, connection: Any, schema: str, function_name: str, version_hash: str
    ) -> FunctionVersionRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT function_name, version_hash, language, returns, arguments_json_b64, "
                "return_columns_json_b64, packages_json_b64, runtime_version, entry_point, "
                "body_sql_b64, definition_text_b64, status "
                f"FROM {self._qualified_name(schema=schema, table=FUNCTION_VERSION_TABLE)} "
                "WHERE function_name = %s AND version_hash = %s",
                [function_name, version_hash],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return FunctionVersionRecord(
            function_name=row[0],
            version_hash=row[1],
            language=row[2],
            returns=row[3],
            arguments_json_b64=row[4],
            return_columns_json_b64=row[5],
            packages_json_b64=row[6],
            runtime_version=row[7],
            entry_point=row[8],
            body_sql_b64=row[9],
            definition_text_b64=row[10],
            status=ModelVersionStatus(row[11]),
        )

    def upsert_seed_version(
        self, *, connection: Any, schema: str, record: SeedVersionRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=SEED_VERSION_TABLE,
                    where_sql="seed_name = %s AND version_hash = %s",
                    params=[record.seed_name, record.version_hash],
                )
                cursor.execute(
                    f"DELETE FROM {self._qualified_name(schema=schema, table=SEED_VERSION_TABLE)} "
                    "WHERE seed_name = %s AND version_hash = %s",
                    [record.seed_name, record.version_hash],
                )
                cursor.execute(
                    f"INSERT INTO {self._qualified_name(schema=schema, table=SEED_VERSION_TABLE)} "
                    "(seed_name, version_hash, identity_metadata_hash, "
                    "identity_metadata_json_b64, status, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, "
                    "COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.seed_name,
                        record.version_hash,
                        record.identity_metadata_hash,
                        record.identity_metadata_json_b64,
                        record.status.value,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_seed_version(
        self, *, connection: Any, schema: str, seed_name: str, version_hash: str
    ) -> SeedVersionRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT seed_name, version_hash, identity_metadata_hash, "
                "identity_metadata_json_b64, status "
                f"FROM {self._qualified_name(schema=schema, table=SEED_VERSION_TABLE)} "
                "WHERE seed_name = %s AND version_hash = %s",
                [seed_name, version_hash],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return SeedVersionRecord(
            seed_name=row[0],
            version_hash=row[1],
            identity_metadata_hash=row[2],
            identity_metadata_json_b64=row[3],
            status=ModelVersionStatus(row[4]),
        )

    def upsert_python_node_version(
        self, *, connection: Any, schema: str, record: PythonNodeVersionRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=PYTHON_NODE_VERSION_TABLE,
                    where_sql="node_type = %s AND node_name = %s AND version_hash = %s",
                    params=[record.node_type, record.node_name, record.version_hash],
                )
                cursor.execute(
                    "DELETE FROM "
                    f"{self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} "
                    "WHERE node_type = %s AND node_name = %s AND version_hash = %s",
                    [record.node_type, record.node_name, record.version_hash],
                )
                cursor.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} "
                    "(node_type, node_name, version_hash, definition_hash, "
                    "identity_metadata_hash, definition_json_b64, identity_metadata_json_b64, "
                    "status, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, "
                    "COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.node_type,
                        record.node_name,
                        record.version_hash,
                        record.definition_hash,
                        record.identity_metadata_hash,
                        record.definition_json_b64,
                        record.identity_metadata_json_b64,
                        record.status.value,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_python_node_version(
        self,
        *,
        connection: Any,
        schema: str,
        node_type: str,
        node_name: str,
        version_hash: str,
    ) -> PythonNodeVersionRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT node_type, node_name, version_hash, definition_hash, "
                "identity_metadata_hash, definition_json_b64, identity_metadata_json_b64, status "
                f"FROM {self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} "
                "WHERE node_type = %s AND node_name = %s AND version_hash = %s",
                [node_type, node_name, version_hash],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return PythonNodeVersionRecord(
            node_type=row[0],
            node_name=row[1],
            version_hash=row[2],
            definition_hash=row[3],
            identity_metadata_hash=row[4],
            definition_json_b64=row[5],
            identity_metadata_json_b64=row[6],
            status=ModelVersionStatus(row[7]),
        )

    def insert_node_result(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        record: NodeResultRecord,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self._qualified_name(schema=schema, table=NODE_RESULTS_TABLE)} "
                "(virtual_environment_name, node_type, node_name, target_database, target_schema, "
                "target_name, run_id, status, payload_json_b64, metadata_json_b64, error_message, "
                "materialized, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s)",
                [
                    virtual_environment_name,
                    record.node_type,
                    record.node_name,
                    record.target_database,
                    record.target_schema,
                    record.target_name,
                    record.run_id,
                    record.status,
                    encode_node_result_json(
                        value=record.payload, label="payload", node_name=record.node_name
                    ),
                    encode_node_result_json(
                        value=record.metadata, label="metadata", node_name=record.node_name
                    ),
                    record.error_message,
                    self._materialized_storage(record.materialized),
                    record.ts,
                ],
            )

    def read_node_results(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        query: NodeResultQuery,
    ) -> tuple[NodeResultEnvelope, ...]:
        if query.limit < 1:
            return ()
        predicates: list[str] = [
            "virtual_environment_name = %s",
            "node_type = %s",
            "node_name = %s",
            self._optional_equality_sql(
                column="target_database", value=query.target_database, placeholder="%s"
            ),
            self._optional_equality_sql(
                column="target_schema", value=query.target_schema, placeholder="%s"
            ),
            self._optional_equality_sql(
                column="target_name", value=query.target_name, placeholder="%s"
            ),
        ]
        params: list[object] = [virtual_environment_name, query.node_type, query.node_name]
        for value in (query.target_database, query.target_schema, query.target_name):
            if value is not None:
                params.append(value)
        if query.statuses is not None:
            placeholders: str = ", ".join("%s" for _ in query.statuses)
            predicates.append(f"status IN ({placeholders})")
            params.extend(query.statuses)
        if query.run_id is not None:
            predicates.append("run_id = %s")
            params.append(query.run_id)
        params.append(query.limit)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT node_type, node_name, run_id, status, payload_json_b64, "
                "metadata_json_b64, error_message, materialized, created_at "
                f"FROM {self._qualified_name(schema=schema, table=NODE_RESULTS_TABLE)} "
                f"WHERE {' AND '.join(predicates)} "
                "ORDER BY created_at DESC, run_id DESC LIMIT %s",
                params,
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(self._node_result_row_to_envelope(row) for row in rows)

    def append_microbatch_event(
        self, *, connection: Any, schema: str, event: MicrobatchEvent
    ) -> None:
        placeholders: str = ", ".join("%s" for _ in MICROBATCH_COLUMNS)
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)} "
                f"({', '.join(MICROBATCH_COLUMNS)}) SELECT {placeholders} "
                "WHERE NOT EXISTS (SELECT 1 FROM "
                f"{self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)} "
                "WHERE event_id = %s)",
                [*MicrobatchEventCodec.values(event), event.event_id],
            )

    def append_microbatch_events(
        self, *, connection: Any, schema: str, events: tuple[MicrobatchEvent, ...]
    ) -> MicrobatchWriteResult:
        if not events:
            return MicrobatchWriteResult(total=0, inserted=0, already_existing=0)
        table: str = self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)
        id_placeholders: str = ", ".join("%s" for _ in events)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT event_id FROM {table} WHERE event_id IN ({id_placeholders})",
                [event.event_id for event in events],
            )
            existing_ids: frozenset[str] = frozenset(str(row[0]) for row in cursor.fetchall())
            missing: tuple[MicrobatchEvent, ...] = tuple(
                event for event in events if event.event_id not in existing_ids
            )
            if missing:
                row_placeholders: str = "(" + ", ".join("%s" for _ in MICROBATCH_COLUMNS) + ")"
                values_sql: str = ", ".join(row_placeholders for _ in missing)
                columns: str = ", ".join(MICROBATCH_COLUMNS)
                params: list[object | None] = []
                for event in missing:
                    params.extend(MicrobatchEventCodec.values(event))
                cursor.execute(
                    f"INSERT INTO {table} ({columns}) SELECT {columns} FROM "
                    f"(VALUES {values_sql}) AS incoming ({columns}) WHERE NOT EXISTS "
                    f"(SELECT 1 FROM {table} existing "
                    "WHERE existing.event_id = incoming.event_id)",
                    params,
                )
        return MicrobatchWriteResult(
            total=len(events), inserted=len(missing), already_existing=len(events) - len(missing)
        )

    def read_microbatch_scope_history(
        self, *, connection: Any, schema: str, scope: MicrobatchScope
    ) -> tuple[MicrobatchEvent, ...]:
        generation_sql: str = (
            ""
            if scope.physical_generation_id == MICROBATCH_GENERATION_WILDCARD
            else "AND physical_generation_id = %s "
        )
        params: list[object] = [scope.scope_kind, scope.scope_key]
        if scope.physical_generation_id != MICROBATCH_GENERATION_WILDCARD:
            params.append(scope.physical_generation_id)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM "
                f"{self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)} "
                "WHERE scope_kind = %s AND scope_key = %s "
                f"{generation_sql}ORDER BY created_at, event_id",
                params,
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(MicrobatchEventCodec.from_row(tuple(row)) for row in rows)

    def read_microbatch_retention_history(
        self, *, connection: Any, schema: str
    ) -> tuple[MicrobatchEvent, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM "
                f"{self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)} "
                "WHERE scope_kind = %s ORDER BY created_at, event_id",
                [VIRTUAL_MICROBATCH_SCOPE_KIND],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(MicrobatchEventCodec.from_row(tuple(row)) for row in rows)

    def read_microbatch_model_history(
        self, *, connection: Any, schema: str, scope: MicrobatchScope
    ) -> tuple[MicrobatchEvent, ...]:
        warehouse_realm: str = scope.physical_generation_id.partition(":")[0]
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM "
                f"{self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)} "
                "WHERE scope_kind = %s AND model_name = %s "
                "AND physical_generation_id LIKE %s ORDER BY created_at, event_id",
                [scope.scope_kind, scope.model_name, f"{warehouse_realm}:%"],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(MicrobatchEventCodec.from_row(tuple(row)) for row in rows)

    def upsert_physical_relation(
        self, *, connection: Any, schema: str, record: PhysicalRelationRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=PHYSICAL_RELATION_TABLE,
                    where_sql="artifact_type = %s AND artifact_name = %s AND version_hash = %s",
                    params=[record.artifact_type.value, record.artifact_name, record.version_hash],
                )
                cursor.execute(
                    "DELETE FROM "
                    f"{self._qualified_name(schema=schema, table=PHYSICAL_RELATION_TABLE)} "
                    "WHERE artifact_type = %s AND artifact_name = %s AND version_hash = %s",
                    [record.artifact_type.value, record.artifact_name, record.version_hash],
                )
                cursor.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema=schema, table=PHYSICAL_RELATION_TABLE)} "
                    "(artifact_type, artifact_name, version_hash, database_name, schema_name, "
                    "relation_name, relation_type, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, "
                    "COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.artifact_type.value,
                        record.artifact_name,
                        record.version_hash,
                        record.database_name,
                        record.schema_name,
                        record.relation_name,
                        record.relation_type,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_physical_relation_for_artifact(
        self,
        *,
        connection: Any,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
        version_hash: str,
    ) -> PhysicalRelationRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT artifact_type, artifact_name, version_hash, database_name, schema_name, "
                "relation_name, relation_type "
                f"FROM {self._qualified_name(schema=schema, table=PHYSICAL_RELATION_TABLE)} "
                "WHERE artifact_type = %s AND artifact_name = %s AND version_hash = %s",
                [artifact_type.value, artifact_name, version_hash],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return PhysicalRelationRecord(
            artifact_type=PhysicalArtifactType(row[0]),
            artifact_name=row[1],
            version_hash=row[2],
            database_name=row[3],
            schema_name=row[4],
            relation_name=row[5],
            relation_type=row[6],
        )

    def list_physical_relations_for_artifact(
        self,
        *,
        connection: Any,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
    ) -> tuple[PhysicalRelationRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT artifact_type, artifact_name, version_hash, database_name, schema_name, "
                "relation_name, relation_type "
                f"FROM {self._qualified_name(schema=schema, table=PHYSICAL_RELATION_TABLE)} "
                "WHERE artifact_type = %s AND artifact_name = %s "
                "ORDER BY updated_at DESC, version_hash DESC",
                [artifact_type.value, artifact_name],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            PhysicalRelationRecord(
                artifact_type=PhysicalArtifactType(row[0]),
                artifact_name=row[1],
                version_hash=row[2],
                database_name=row[3],
                schema_name=row[4],
                relation_name=row[5],
                relation_type=row[6],
            )
            for row in rows
        )

    def upsert_physical_relation_ancestry(
        self, *, connection: Any, schema: str, record: PhysicalRelationAncestryRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=PHYSICAL_RELATION_ANCESTRY_TABLE,
                    where_sql="model_name = %s AND version_hash = %s",
                    params=[record.model_name, record.version_hash],
                )
                cursor.execute(
                    "DELETE FROM "
                    f"{self._qualified_name(schema=schema, table=PHYSICAL_RELATION_ANCESTRY_TABLE)}"
                    " "
                    "WHERE model_name = %s AND version_hash = %s",
                    [record.model_name, record.version_hash],
                )
                cursor.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema=schema, table=PHYSICAL_RELATION_ANCESTRY_TABLE)}"
                    " "
                    "(model_name, version_hash, parent_model_name, parent_version_hash, "
                    "seed_strategy, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, "
                    "COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.model_name,
                        record.version_hash,
                        record.parent_model_name,
                        record.parent_version_hash,
                        record.seed_strategy,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_physical_relation_ancestry(
        self, *, connection: Any, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationAncestryRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT model_name, version_hash, parent_model_name, parent_version_hash, "
                "seed_strategy "
                "FROM "
                f"{self._qualified_name(schema=schema, table=PHYSICAL_RELATION_ANCESTRY_TABLE)} "
                "WHERE model_name = %s AND version_hash = %s",
                [model_name, version_hash],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return PhysicalRelationAncestryRecord(
            model_name=row[0],
            version_hash=row[1],
            parent_model_name=row[2],
            parent_version_hash=row[3],
            seed_strategy=row[4],
        )

    def upsert_virtual_environment(
        self, *, connection: Any, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                self._upsert_virtual_environment_record(cursor=cursor, schema=schema, record=record)
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_virtual_environment(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT virtual_environment_name, status, baseline_virtual_environment_name, "
                "finalized_at "
                f"FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
                "WHERE virtual_environment_name = %s",
                [virtual_environment_name],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return VirtualEnvironmentRecord(
            virtual_environment_name=row[0],
            status=VirtualEnvironmentStatus(row[1]),
            baseline_virtual_environment_name=row[2],
            finalized_at=row[3],
        )

    def list_virtual_environments(
        self, *, connection: Any, schema: str
    ) -> tuple[VirtualEnvironmentRetentionRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT virtual_environment_name, status, updated_at "
                f"FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
                "ORDER BY updated_at DESC, virtual_environment_name DESC"
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name=row[0],
                status=VirtualEnvironmentStatus(row[1]),
                updated_at=row[2],
            )
            for row in rows
        )

    def delete_virtual_environment(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(
                    "DELETE FROM "
                    + self._qualified_name(
                        schema=schema,
                        table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
                    )
                    + " "
                    "WHERE virtual_environment_name = %s",
                    [virtual_environment_name],
                )
                cursor.execute(
                    "DELETE FROM "
                    + self._qualified_name(
                        schema=schema,
                        table=SOURCE_FRESHNESS_OBSERVATION_TABLE,
                    )
                    + " "
                    "WHERE virtual_environment_name = %s",
                    [virtual_environment_name],
                )
                cursor.execute(
                    "DELETE FROM "
                    f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
                    "WHERE virtual_environment_name = %s",
                    [virtual_environment_name],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def replace_virtual_environment_node_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_ref_groups(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            refs_by_node_type={node_type: refs},
        )

    def replace_virtual_environment_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                self._replace_virtual_environment_node_ref_groups(
                    cursor=cursor,
                    schema=schema,
                    virtual_environment_name=virtual_environment_name,
                    refs_by_node_type=refs_by_node_type,
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def upsert_virtual_environment_and_replace_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                self._upsert_virtual_environment_record(cursor=cursor, schema=schema, record=record)
                self._replace_virtual_environment_node_ref_groups(
                    cursor=cursor,
                    schema=schema,
                    virtual_environment_name=record.virtual_environment_name,
                    refs_by_node_type=refs_by_node_type,
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def upsert_virtual_environment_and_replace_node_ref_groups_if_locks_owned(
        self,
        *,
        connection: Any,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
        leases: tuple[StateLockLease, ...],
        checkpoint: VirtualEnvironmentCheckpointRecord | None = None,
        checkpoint_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (),
        checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
        checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (),
    ) -> bool:
        validate_conditional_virtual_environment_publication(
            record=record,
            refs_by_node_type=refs_by_node_type,
            checkpoint=checkpoint,
            checkpoint_refs=checkpoint_refs,
            checkpoint_function_refs=checkpoint_function_refs,
            checkpoint_seed_refs=checkpoint_seed_refs,
        )
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                lease: StateLockLease
                for lease in leases:
                    lock_table: str = self._qualified_name(schema=schema, table=LOCK_TABLE)
                    cursor.execute(
                        f"SELECT lock_key FROM {lock_table} "
                        "WHERE lock_key = %s AND owner_id = %s "
                        "AND expires_at > CURRENT_TIMESTAMP FOR UPDATE",
                        [lease.lock_key, lease.owner_id],
                    )
                    if cursor.fetchone() is None:
                        cursor.execute("ROLLBACK")
                        return False
                self._upsert_virtual_environment_record(cursor=cursor, schema=schema, record=record)
                self._replace_virtual_environment_node_ref_groups(
                    cursor=cursor,
                    schema=schema,
                    virtual_environment_name=record.virtual_environment_name,
                    refs_by_node_type=refs_by_node_type,
                )
                if checkpoint is not None:
                    self._insert_virtual_environment_checkpoint_rows(
                        cursor=cursor,
                        schema=schema,
                        checkpoint=checkpoint,
                        refs=checkpoint_refs,
                        function_refs=checkpoint_function_refs,
                        seed_refs=checkpoint_seed_refs,
                    )
                cursor.execute("COMMIT")
                return True
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_virtual_environment_node_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
    ) -> tuple[VirtualEnvironmentNodeRefRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT virtual_environment_name, node_type, node_name, version_hash "
                "FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = %s AND node_type = %s ORDER BY node_name",
                [virtual_environment_name, node_type],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=row[0],
                node_type=row[1],
                node_name=row[2],
                version_hash=row[3],
            )
            for row in rows
        )

    def upsert_virtual_environment_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentNodeRefRecord,
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "(virtual_environment_name, node_type, node_name, version_hash, updated_at) "
                "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) "
                "ON CONFLICT (virtual_environment_name, node_type, node_name) "
                "DO UPDATE SET version_hash = excluded.version_hash, "
                "updated_at = CURRENT_TIMESTAMP",
                [ref.virtual_environment_name, ref.node_type, ref.node_name, ref.version_hash],
            )

    def replace_virtual_environment_model_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="model",
            refs=tuple(
                VirtualEnvironmentNodeRefRecord(
                    virtual_environment_name=ref.virtual_environment_name,
                    node_type="model",
                    node_name=ref.model_name,
                    version_hash=ref.version_hash,
                )
                for ref in refs
            ),
        )

    def get_virtual_environment_model_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = self.get_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="model",
        )
        return tuple(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                model_name=ref.node_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        )

    def replace_virtual_environment_function_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        ref: VirtualEnvironmentFunctionRefRecord
        for ref in refs:
            if ref.node_type not in {
                CompiledResourceType.UDF,
                CompiledResourceType.TABLE_FN,
            }:
                raise StateBackendConfigError("Function ref node_type must be 'udf' or 'table_fn'")
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]] = {}
        for node_type in ("udf", "table_fn"):
            node_refs: list[VirtualEnvironmentNodeRefRecord] = []
            for ref in refs:
                if ref.node_type == node_type:
                    node_refs.append(
                        VirtualEnvironmentNodeRefRecord(
                            virtual_environment_name=ref.virtual_environment_name,
                            node_type=ref.node_type,
                            node_name=ref.function_name,
                            version_hash=ref.version_hash,
                        )
                    )
            refs_by_node_type[node_type] = tuple(node_refs)
        self.replace_virtual_environment_node_ref_groups(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            refs_by_node_type=refs_by_node_type,
        )

    def get_virtual_environment_function_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = (
            *self.get_virtual_environment_node_refs(
                connection=connection,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                node_type="udf",
            ),
            *self.get_virtual_environment_node_refs(
                connection=connection,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                node_type="table_fn",
            ),
        )
        return tuple(
            VirtualEnvironmentFunctionRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                function_name=ref.node_name,
                version_hash=ref.version_hash,
            )
            for ref in sorted(refs, key=lambda item: (item.node_type, item.node_name))
        )

    def replace_virtual_environment_seed_refs(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="seed",
            refs=tuple(
                VirtualEnvironmentNodeRefRecord(
                    virtual_environment_name=ref.virtual_environment_name,
                    node_type="seed",
                    node_name=ref.seed_name,
                    version_hash=ref.version_hash,
                )
                for ref in refs
            ),
        )

    def get_virtual_environment_seed_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentSeedRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = self.get_virtual_environment_node_refs(
            connection=connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            node_type="seed",
        )
        return tuple(
            VirtualEnvironmentSeedRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                seed_name=ref.node_name,
                version_hash=ref.version_hash,
            )
            for ref in refs
        )

    def upsert_virtual_environment_python_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentPythonNodeRefRecord,
    ) -> None:
        self.upsert_virtual_environment_node_ref(
            connection=connection,
            schema=schema,
            ref=VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.node_name,
                version_hash=ref.version_hash,
            ),
        )

    def get_virtual_environment_python_node_refs(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentPythonNodeRefRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT virtual_environment_name, node_type, node_name, version_hash "
                "FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = %s "
                "AND node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
                "ORDER BY node_type, node_name",
                [virtual_environment_name],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=row[0],
                node_type=row[1],
                node_name=row[2],
                version_hash=row[3],
            )
            for row in rows
        )

    def count_unreferenced_python_node_versions(self, *, connection: Any, schema: str) -> int:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) "
                "FROM "
                f"{self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} versions "
                "WHERE NOT EXISTS ("
                "SELECT 1 "
                "FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "refs "
                "WHERE refs.node_type = versions.node_type "
                "AND refs.node_name = versions.node_name "
                "AND refs.version_hash = versions.version_hash)"
            )
            row: tuple[Any, ...] = cursor.fetchone()
        return int(row[0])

    def prune_unreferenced_python_node_versions(self, *, connection: Any, schema: str) -> int:
        before_count: int = self.count_unreferenced_python_node_versions(
            connection=connection, schema=schema
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} "
                "AS versions "
                "WHERE NOT EXISTS ("
                "SELECT 1 "
                "FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "refs "
                "WHERE refs.node_type = versions.node_type "
                "AND refs.node_name = versions.node_name "
                "AND refs.version_hash = versions.version_hash)"
            )
        return before_count

    def replace_virtual_environment_source_freshness(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        records: tuple[SourceFreshnessRecord, ...],
    ) -> None:
        self._validate_source_freshness_records(
            virtual_environment_name=virtual_environment_name,
            records=records,
        )
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(
                    "DELETE FROM "
                    + self._qualified_name(
                        schema=schema,
                        table=SOURCE_FRESHNESS_OBSERVATION_TABLE,
                    )
                    + " "
                    "WHERE virtual_environment_name = %s",
                    [virtual_environment_name],
                )
                record: SourceFreshnessRecord
                for record in records:
                    cursor.execute(
                        "INSERT INTO "
                        + self._qualified_name(
                            schema=schema,
                            table=SOURCE_FRESHNESS_OBSERVATION_TABLE,
                        )
                        + " "
                        "(virtual_environment_name, source_name, strategy, value_kind, "
                        "data_version, data_version_hash, observed_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                        [
                            record.virtual_environment_name,
                            record.source_name,
                            record.strategy,
                            record.value_kind,
                            record.data_version,
                            record.data_version_hash,
                            record.observed_at,
                        ],
                    )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_virtual_environment_source_freshness(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[SourceFreshnessRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT virtual_environment_name, source_name, strategy, value_kind, "
                "data_version, data_version_hash, observed_at "
                "FROM "
                f"{self._qualified_name(schema=schema, table=SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
                "WHERE virtual_environment_name = %s ORDER BY source_name",
                [virtual_environment_name],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            SourceFreshnessRecord(
                virtual_environment_name=row[0],
                source_name=row[1],
                strategy=row[2],
                value_kind=row[3],
                data_version=row[4],
                data_version_hash=row[5],
                observed_at=row[6],
            )
            for row in rows
        )

    def create_virtual_environment_checkpoint(
        self,
        *,
        connection: Any,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
        seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (),
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                self._insert_virtual_environment_checkpoint_rows(
                    cursor=cursor,
                    schema=schema,
                    checkpoint=checkpoint,
                    refs=refs,
                    function_refs=function_refs,
                    seed_refs=seed_refs,
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def _insert_virtual_environment_checkpoint_rows(
        self,
        *,
        cursor: Any,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...],
        seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
    ) -> None:
        checkpoint_table: str = self._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE
        )
        model_ref_table: str = self._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE
        )
        function_ref_table: str = self._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE
        )
        seed_ref_table: str = self._qualified_name(
            schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE
        )
        cursor.execute(
            f"INSERT INTO {checkpoint_table} "
            "(checkpoint_id, virtual_environment_name, created_at) "
            "VALUES (%s, %s, CURRENT_TIMESTAMP)",
            [checkpoint.checkpoint_id, checkpoint.virtual_environment_name],
        )
        ref: VirtualEnvironmentCheckpointModelRefRecord
        for ref in refs:
            cursor.execute(
                f"INSERT INTO {model_ref_table} "
                "(checkpoint_id, model_name, version_hash) VALUES (%s, %s, %s)",
                [ref.checkpoint_id, ref.model_name, ref.version_hash],
            )
        function_ref: VirtualEnvironmentCheckpointFunctionRefRecord
        for function_ref in function_refs:
            cursor.execute(
                f"INSERT INTO {function_ref_table} "
                "(checkpoint_id, function_name, version_hash) VALUES (%s, %s, %s)",
                [function_ref.checkpoint_id, function_ref.function_name, function_ref.version_hash],
            )
        seed_ref: VirtualEnvironmentCheckpointSeedRefRecord
        for seed_ref in seed_refs:
            cursor.execute(
                f"INSERT INTO {seed_ref_table} "
                "(checkpoint_id, seed_name, version_hash) VALUES (%s, %s, %s)",
                [seed_ref.checkpoint_id, seed_ref.seed_name, seed_ref.version_hash],
            )

    def list_virtual_environment_checkpoints(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT checkpoint_id, virtual_environment_name, created_at "
                "FROM "
                + self._qualified_name(
                    schema=schema,
                    table=VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
                )
                + " "
                "WHERE virtual_environment_name = %s ORDER BY created_at DESC, checkpoint_id DESC",
                [virtual_environment_name],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentCheckpointRecord(
                checkpoint_id=row[0],
                virtual_environment_name=row[1],
                created_at=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_model_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]:
        with connection.cursor() as cursor:
            checkpoint_model_ref_table: str = self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
            )
            cursor.execute(
                f"SELECT checkpoint_id, model_name, version_hash "
                f"FROM {checkpoint_model_ref_table} "
                "WHERE checkpoint_id = %s ORDER BY model_name",
                [checkpoint_id],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id=row[0],
                model_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_function_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        with connection.cursor() as cursor:
            checkpoint_function_ref_table: str = self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
            )
            cursor.execute(
                f"SELECT checkpoint_id, function_name, version_hash "
                f"FROM {checkpoint_function_ref_table} "
                "WHERE checkpoint_id = %s ORDER BY function_name",
                [checkpoint_id],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentCheckpointFunctionRefRecord(
                checkpoint_id=row[0],
                function_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_seed_refs(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]:
        with connection.cursor() as cursor:
            checkpoint_seed_ref_table: str = self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
            )
            cursor.execute(
                f"SELECT checkpoint_id, seed_name, version_hash "
                f"FROM {checkpoint_seed_ref_table} "
                "WHERE checkpoint_id = %s ORDER BY seed_name",
                [checkpoint_id],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id=row[0],
                seed_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def delete_virtual_environment_checkpoint(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                checkpoint_function_ref_table: str = self._qualified_name(
                    schema=schema,
                    table=VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
                )
                checkpoint_model_ref_table: str = self._qualified_name(
                    schema=schema,
                    table=VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
                )
                checkpoint_seed_ref_table: str = self._qualified_name(
                    schema=schema,
                    table=VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
                )
                cursor.execute(
                    f"DELETE FROM {checkpoint_seed_ref_table} WHERE checkpoint_id = %s",
                    [checkpoint_id],
                )
                cursor.execute(
                    f"DELETE FROM {checkpoint_function_ref_table} WHERE checkpoint_id = %s",
                    [checkpoint_id],
                )
                cursor.execute(
                    f"DELETE FROM {checkpoint_model_ref_table} WHERE checkpoint_id = %s",
                    [checkpoint_id],
                )
                cursor.execute(
                    "DELETE FROM "
                    + self._qualified_name(
                        schema=schema,
                        table=VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
                    )
                    + " "
                    "WHERE checkpoint_id = %s",
                    [checkpoint_id],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def upsert_state_operation(
        self, *, connection: Any, schema: str, record: StateOperationRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                existing_created_at: datetime | None = self._created_at_for_key(
                    cursor=cursor,
                    schema=schema,
                    table_name=STATE_OPERATION_TABLE,
                    where_sql="operation_id = %s",
                    params=[record.operation_id],
                )
                cursor.execute(
                    "DELETE FROM "
                    f"{self._qualified_name(schema=schema, table=STATE_OPERATION_TABLE)} "
                    "WHERE operation_id = %s",
                    [record.operation_id],
                )
                cursor.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema=schema, table=STATE_OPERATION_TABLE)} "
                    "(operation_id, operation_type, status, virtual_environment_name, "
                    "created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                    [
                        record.operation_id,
                        record.operation_type.value,
                        record.status.value,
                        record.virtual_environment_name,
                        existing_created_at,
                    ],
                )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def get_state_operation(
        self, *, connection: Any, schema: str, operation_id: str
    ) -> StateOperationRecord | None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT operation_id, operation_type, status, virtual_environment_name "
                f"FROM {self._qualified_name(schema=schema, table=STATE_OPERATION_TABLE)} "
                "WHERE operation_id = %s",
                [operation_id],
            )
            row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return StateOperationRecord(
            operation_id=row[0],
            operation_type=StateOperationType(row[1]),
            status=StateOperationStatus(row[2]),
            virtual_environment_name=row[3],
        )

    def create_state_operation_event(
        self, *, connection: Any, schema: str, record: StateOperationEventRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO "
                f"{self._qualified_name(schema=schema, table=STATE_OPERATION_EVENT_TABLE)} "
                "(event_id, operation_id, action, status, message, created_at) "
                "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                [
                    record.event_id,
                    record.operation_id,
                    record.action,
                    record.status.value,
                    record.message,
                ],
            )

    def create_reconcile_event(
        self, *, connection: Any, schema: str, record: ReconcileEventRecord
    ) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self._qualified_name(schema=schema, table=RECONCILE_EVENT_TABLE)} "
                "(event_id, action, status, message, created_at) "
                "VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)",
                [record.event_id, record.action.value, record.status.value, record.message],
            )

    def acquire_lock(
        self,
        *,
        connection: Any,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(
                    f"DELETE FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                    "WHERE lock_key = %s AND expires_at <= CURRENT_TIMESTAMP",
                    [lock_key],
                )
                cursor.execute(
                    f"INSERT INTO {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                    "(lock_key, owner_id, expires_at, created_at, updated_at) "
                    "VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    [lock_key, owner_id, expires_at],
                )
                cursor.execute("COMMIT")
                return True
            except BaseException:
                cursor.execute("ROLLBACK")
                cursor.execute(
                    f"SELECT owner_id FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                    "WHERE lock_key = %s AND expires_at > CURRENT_TIMESTAMP",
                    [lock_key],
                )
                if cursor.fetchone() is not None:
                    return False
                raise

    def release_lock(self, *, connection: Any, schema: str, lock_key: str, owner_id: str) -> bool:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(
                    f"SELECT owner_id FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                    "WHERE lock_key = %s AND owner_id = %s",
                    [lock_key, owner_id],
                )
                if cursor.fetchone() is None:
                    cursor.execute("COMMIT")
                    return False
                cursor.execute(
                    f"DELETE FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                    "WHERE lock_key = %s AND owner_id = %s",
                    [lock_key, owner_id],
                )
                cursor.execute("COMMIT")
                return True
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def renew_lock(
        self,
        *,
        connection: Any,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "SET expires_at = %s, updated_at = CURRENT_TIMESTAMP "
                "WHERE lock_key = %s AND owner_id = %s AND expires_at > CURRENT_TIMESTAMP "
                "RETURNING lock_key",
                [expires_at, lock_key, owner_id],
            )
            return cursor.fetchone() is not None

    def list_active_locks(self, *, connection: Any, schema: str) -> tuple[StateLockRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT lock_key, owner_id, expires_at FROM "
                f"{self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "WHERE expires_at > CURRENT_TIMESTAMP ORDER BY lock_key"
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            StateLockRecord(lock_key=row[0], owner_id=row[1], expires_at=row[2]) for row in rows
        )

    def list_expired_locks(self, *, connection: Any, schema: str) -> tuple[StateLockRecord, ...]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT lock_key, owner_id, expires_at FROM "
                f"{self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "WHERE expires_at <= CURRENT_TIMESTAMP ORDER BY lock_key"
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            StateLockRecord(lock_key=row[0], owner_id=row[1], expires_at=row[2]) for row in rows
        )

    def delete_lock(self, *, connection: Any, schema: str, lock_key: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=LOCK_TABLE)} WHERE lock_key = %s",
                [lock_key],
            )
        connection.commit()

    def list_state_backups(self, *, connection: Any, schema: str) -> tuple[StateBackupRecord, ...]:
        prefix: str = f"{schema}__backup_%"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT s.schema_name, e.backup_id, MAX(e.created_at) "
                "FROM information_schema.schemata s "
                "LEFT JOIN "
                f"{self._qualified_name(schema=schema, table=STATE_MIGRATION_EVENTS_TABLE)} e "
                "ON s.schema_name = %s || e.backup_id "
                "WHERE s.schema_name LIKE %s "
                "GROUP BY s.schema_name, e.backup_id ORDER BY s.schema_name DESC",
                [f"{schema}__backup_", prefix],
            )
            rows: list[tuple[Any, ...]] = cursor.fetchall()
        return tuple(
            StateBackupRecord(
                backup_id=row[1] or str(row[0]).removeprefix(f"{schema}__backup_"),
                schema_name=row[0],
                created_at=row[2],
            )
            for row in rows
        )

    def delete_state_backup(self, *, connection: Any, schema: str, backup_id: str) -> None:
        backup_schema: str = self._backup_schema_name(schema=schema, backup_id_value=backup_id)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {self._quote_identifier(backup_schema)} CASCADE")
        connection.commit()

    def _latest_backup_id(self, *, connection: Any, schema: str) -> str:
        prefix: str = f"{schema}__backup_%"
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE %s "
                "ORDER BY schema_name DESC LIMIT 1",
                [prefix],
            )
            row: tuple[str] | None = cursor.fetchone()
        if row is None:
            raise StateBackupNotFoundError("No state backup is available for rollback")
        return row[0].removeprefix(f"{schema}__backup_")

    def _schema_exists(self, *, connection: Any, schema: str) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
                [schema],
            )
            row: tuple[str] | None = cursor.fetchone()
        return row is not None

    def _record_event(
        self,
        *,
        cursor: Any,
        schema: str,
        action: StateMigrationAction,
        backup_id_value: str | None,
        status: StateMigrationStatus,
        message: str | None,
    ) -> None:
        cursor.execute(
            "INSERT INTO "
            f"{self._qualified_name(schema=schema, table=STATE_MIGRATION_EVENTS_TABLE)} "
            "(event_id, action, backup_id, status, message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            [event_id(), action.value, backup_id_value, status.value, message],
        )

    def _create_additional_state_tables(self, *, cursor: Any, schema: str) -> None:
        table_name: str
        columns: dict[str, StateColumnType]
        for table_name, columns in STATE_TABLE_COLUMNS.items():
            if table_name in {STATE_VERSION_TABLE, STATE_MIGRATION_EVENTS_TABLE}:
                continue
            column_sql: str = ", ".join(
                f"{self._quote_identifier(column_name)} {self._state_column_sql_type(column_type)}"
                for column_name, column_type in columns.items()
            )
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS "
                f"{self._qualified_name(schema=schema, table=table_name)} "
                f"({column_sql})"
            )
            column_name: str
            column_type: StateColumnType
            for column_name, column_type in columns.items():
                cursor.execute(
                    f"ALTER TABLE {self._qualified_name(schema=schema, table=table_name)} "
                    f"ADD COLUMN IF NOT EXISTS {self._quote_identifier(column_name)} "
                    f"{self._state_column_sql_type(column_type)}"
                )
        self._create_state_indexes(cursor=cursor, schema=schema)

    def _create_state_indexes(self, *, cursor: Any, schema: str) -> None:
        table_name: str
        indexes: dict[str, tuple[str, ...]]
        for table_name, indexes in STATE_TABLE_INDEXES.items():
            index_name: str
            columns: tuple[str, ...]
            for index_name, columns in indexes.items():
                column_sql: str = ", ".join(self._quote_identifier(column) for column in columns)
                unique_sql: str = "" if index_name in NON_UNIQUE_STATE_INDEXES else "UNIQUE "
                cursor.execute(
                    f"CREATE {unique_sql}INDEX IF NOT EXISTS {self._quote_identifier(index_name)} "
                    f"ON {self._qualified_name(schema=schema, table=table_name)} ({column_sql})"
                )

    def _created_at_for_key(
        self,
        *,
        cursor: Any,
        schema: str,
        table_name: str,
        where_sql: str,
        params: list[object],
    ) -> datetime | None:
        cursor.execute(
            f"SELECT created_at FROM {self._qualified_name(schema=schema, table=table_name)} "
            f"WHERE {where_sql}",
            params,
        )
        row: tuple[Any, ...] | None = cursor.fetchone()
        if row is None:
            return None
        return row[0]

    def _state_column_sql_type(self, column_type: StateColumnType) -> str:
        match column_type:
            case StateColumnType.INTEGER:
                return "INTEGER"
            case StateColumnType.TEXT:
                return "TEXT"
            case StateColumnType.TIMESTAMP:
                return "TIMESTAMP"
        raise StateBackendConfigError(f"Unsupported state column type: {column_type}")

    def _node_result_row_to_envelope(self, row: tuple[Any, ...]) -> NodeResultEnvelope:
        node_name: str = str(row[1])
        metadata: object = decode_node_result_json(
            value=str(row[5]), label="metadata", node_name=node_name
        )
        normalized_metadata: dict[str, object] = (
            {str(key): value for key, value in metadata.items()}
            if isinstance(metadata, dict)
            else {}
        )
        return NodeResultEnvelope(
            node_type=str(row[0]),
            node_name=node_name,
            run_id=str(row[2]),
            status=str(row[3]),
            payload=decode_node_result_json(
                value=str(row[4]), label="payload", node_name=node_name
            ),
            metadata=normalized_metadata,
            error_message=str(row[6]) if row[6] is not None else None,
            materialized=self._parse_materialized(row[7]),
            ts=row[8],
        )

    def _optional_equality_sql(self, *, column: str, value: object | None, placeholder: str) -> str:
        if value is None:
            return f"{column} IS NULL"
        return f"{column} = {placeholder}"

    def _materialized_storage(self, value: bool | None) -> str | None:
        if value is None:
            return None
        return "true" if value else "false"

    def _parse_materialized(self, value: object) -> bool | None:
        if value is None:
            return None
        return str(value).lower() == STATE_BOOLEAN_TRUE

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _qualified_name(self, *, schema: str, table: str) -> str:
        return f"{self._quote_identifier(schema)}.{self._quote_identifier(table)}"

    def _validate_source_freshness_records(
        self,
        *,
        virtual_environment_name: str,
        records: tuple[SourceFreshnessRecord, ...],
    ) -> None:
        seen_source_names: set[str] = set()
        record: SourceFreshnessRecord
        for record in records:
            if record.virtual_environment_name != virtual_environment_name:
                raise StateBackendConfigError(
                    "Source freshness record virtual_environment_name must match replacement "
                    "virtual_environment_name"
                )
            if record.source_name in seen_source_names:
                raise StateBackendConfigError(
                    f"Duplicate source freshness record for source '{record.source_name}'"
                )
            seen_source_names.add(record.source_name)

    def _validate_node_ref_replacement(
        self,
        *,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        seen_node_names: set[str] = set()
        ref: VirtualEnvironmentNodeRefRecord
        for ref in refs:
            if ref.virtual_environment_name != virtual_environment_name:
                raise StateBackendConfigError(
                    "Node ref virtual_environment_name must match replacement "
                    "virtual_environment_name"
                )
            if ref.node_type != node_type:
                raise StateBackendConfigError("Node ref node_type must match replacement node_type")
            if ref.node_name in seen_node_names:
                raise StateBackendConfigError(
                    f"Duplicate node ref for node type '{node_type}' and name '{ref.node_name}'"
                )
            seen_node_names.add(ref.node_name)

    def _upsert_virtual_environment_record(
        self, *, cursor: Any, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        existing_created_at: datetime | None = self._created_at_for_key(
            cursor=cursor,
            schema=schema,
            table_name=VIRTUAL_ENVIRONMENT_TABLE,
            where_sql="virtual_environment_name = %s",
            params=[record.virtual_environment_name],
        )
        cursor.execute(
            f"DELETE FROM {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
            "WHERE virtual_environment_name = %s",
            [record.virtual_environment_name],
        )
        cursor.execute(
            f"INSERT INTO {self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
            "(virtual_environment_name, status, baseline_virtual_environment_name, "
            "created_at, updated_at, finalized_at) "
            "VALUES (%s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP, %s)",
            [
                record.virtual_environment_name,
                record.status.value,
                record.baseline_virtual_environment_name,
                existing_created_at,
                record.finalized_at,
            ],
        )

    def _replace_virtual_environment_node_ref_groups(
        self,
        *,
        cursor: Any,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        node_type: str
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...]
        for node_type, refs in refs_by_node_type.items():
            self._validate_node_ref_replacement(
                virtual_environment_name=virtual_environment_name,
                node_type=node_type,
                refs=refs,
            )
            cursor.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = %s AND node_type = %s",
                [virtual_environment_name, node_type],
            )
            ref: VirtualEnvironmentNodeRefRecord
            for ref in refs:
                cursor.execute(
                    "INSERT INTO "
                    + self._qualified_name(
                        schema=schema,
                        table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
                    )
                    + " "
                    "(virtual_environment_name, node_type, node_name, version_hash, "
                    "updated_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (virtual_environment_name, node_type, node_name) "
                    "DO UPDATE SET version_hash = excluded.version_hash, "
                    "updated_at = CURRENT_TIMESTAMP",
                    [
                        ref.virtual_environment_name,
                        ref.node_type,
                        ref.node_name,
                        ref.version_hash,
                    ],
                )

    def _backup_schema_name(self, *, schema: str, backup_id_value: str) -> str:
        return f"{schema}__backup_{backup_id_value}"

    def _state_type_matches(self, *, actual_type: str, expected_type: StateColumnType) -> bool:
        actual: str = actual_type.lower()
        match expected_type:
            case StateColumnType.INTEGER:
                return actual in POSTGRES_INTEGER_TYPES
            case StateColumnType.TEXT:
                return actual in POSTGRES_TEXT_TYPES
            case StateColumnType.TIMESTAMP:
                return actual.startswith("timestamp")
        return False


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
