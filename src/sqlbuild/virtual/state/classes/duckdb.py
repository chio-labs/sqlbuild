"""DuckDB virtual-state backend."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.executor.node_results.main.decode_json import decode_node_result_json
from sqlbuild.executor.node_results.main.encode_json import encode_node_result_json
from sqlbuild.executor.node_results.models import NodeResultEnvelope, NodeResultRecord
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import (
    CURRENT_STATE_SCHEMA_VERSION,
    FUNCTION_VERSION_TABLE,
    LOCK_TABLE,
    MODEL_VERSION_TABLE,
    NODE_RESULTS_TABLE,
    PHYSICAL_RELATION_ANCESTRY_TABLE,
    PHYSICAL_RELATION_TABLE,
    PYTHON_NODE_VERSION_TABLE,
    RECONCILE_EVENT_TABLE,
    SEED_VERSION_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
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
from sqlbuild.virtual.state.helpers.events import backup_id, event_id
from sqlbuild.virtual.state.helpers.validation import build_validation_result
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


class DuckDbStateBackend(StateBackend):
    """DuckDB implementation for virtual state."""

    def connect(self, config: dict[str, object]) -> Any:
        import duckdb

        database: object | None = config.get("database")
        if not isinstance(database, str) or not database:
            raise StateBackendConfigError("DuckDB state backend requires state.connection.database")
        return duckdb.connect(database)

    def close(self, connection: Any) -> None:
        connection.close()

    def initialize(self, connection: Any, *, schema: str, sqlbuild_version: str) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {self._qualified_name(schema, STATE_VERSION_TABLE)} ("
                "schema_version INTEGER NOT NULL, "
                "sqlbuild_version TEXT NOT NULL, "
                "updated_at TIMESTAMP NOT NULL"
                ")"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS "
                f"{self._qualified_name(schema, STATE_MIGRATION_EVENTS_TABLE)} ("
                "event_id TEXT NOT NULL, "
                "action TEXT NOT NULL, "
                "backup_id TEXT, "
                "status TEXT NOT NULL, "
                "message TEXT, "
                "created_at TIMESTAMP NOT NULL"
                ")"
            )
            self._create_additional_state_tables(connection, schema=schema)
            connection.execute(f"DELETE FROM {self._qualified_name(schema, STATE_VERSION_TABLE)}")
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, STATE_VERSION_TABLE)} "
                "(schema_version, sqlbuild_version, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                [CURRENT_STATE_SCHEMA_VERSION, sqlbuild_version],
            )
            self._record_event(
                connection,
                schema=schema,
                action=StateMigrationAction.INIT,
                backup_id_value=None,
                status=StateMigrationStatus.SUCCESS,
                message=None,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def validate_schema(self, connection: Any, *, schema: str) -> StateSchemaValidationResult:
        tables: set[str] = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
                [schema],
            ).fetchall()
        }
        columns_by_table: dict[str, dict[str, str]] = {}
        for row in connection.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = ?",
            [schema],
        ).fetchall():
            columns_by_table.setdefault(row[0], {})[row[1]] = row[2]
        indexes_by_table: dict[str, set[str]] = {}
        for row in connection.execute(
            "SELECT table_name, index_name FROM duckdb_indexes() WHERE schema_name = ?",
            [schema],
        ).fetchall():
            indexes_by_table.setdefault(row[0], set()).add(row[1])
        return build_validation_result(
            existing_tables=tables,
            columns_by_table=columns_by_table,
            expected_columns=STATE_TABLE_COLUMNS,
            type_matches=self._state_type_matches,
            expected_indexes=STATE_TABLE_INDEXES,
            existing_indexes_by_table=indexes_by_table,
        )

    def create_backup(self, connection: Any, *, schema: str) -> str:
        validation: StateSchemaValidationResult = self.validate_schema(connection, schema=schema)
        if not validation.valid:
            raise StateSchemaInvalidError("Cannot backup invalid state schema")
        backup_id_value: str = backup_id()
        backup_schema: str = self._backup_schema_name(
            schema=schema,
            backup_id_value=backup_id_value,
        )
        connection.execute("BEGIN")
        try:
            connection.execute(f"CREATE SCHEMA {self._quote_identifier(backup_schema)}")
            table_name: str
            for table_name in STATE_TABLES:
                connection.execute(
                    f"CREATE TABLE {self._qualified_name(backup_schema, table_name)} AS "
                    f"SELECT * FROM {self._qualified_name(schema, table_name)}"
                )
            self._record_event(
                connection,
                schema=schema,
                action=StateMigrationAction.BACKUP,
                backup_id_value=backup_id_value,
                status=StateMigrationStatus.SUCCESS,
                message=None,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        return backup_id_value

    def rollback(self, connection: Any, *, schema: str, backup_id: str | None = None) -> str:
        backup_id_value: str = backup_id or self._latest_backup_id(connection, schema=schema)
        backup_schema: str = self._backup_schema_name(
            schema=schema,
            backup_id_value=backup_id_value,
        )
        if not self._schema_exists(connection, schema=backup_schema):
            raise StateBackupNotFoundError(f"State backup schema '{backup_schema}' does not exist")
        connection.execute("BEGIN")
        try:
            table_name: str
            for table_name in STATE_TABLES:
                connection.execute(
                    f"DROP TABLE IF EXISTS {self._qualified_name(schema, table_name)}"
                )
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
            for table_name in STATE_TABLES:
                connection.execute(
                    f"CREATE TABLE {self._qualified_name(schema, table_name)} AS "
                    f"SELECT * FROM {self._qualified_name(backup_schema, table_name)}"
                )
            self._create_state_indexes(connection, schema=schema)
            self._record_event(
                connection,
                schema=schema,
                action=StateMigrationAction.ROLLBACK,
                backup_id_value=backup_id_value,
                status=StateMigrationStatus.SUCCESS,
                message=None,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        return backup_id_value

    def reset(self, connection: Any, *, schema: str) -> None:
        connection.execute("BEGIN")
        try:
            for table_name in STATE_TABLES:
                connection.execute(
                    f"DROP TABLE IF EXISTS {self._qualified_name(schema, table_name)}"
                )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def upsert_model_version(
        self, connection: Any, *, schema: str, record: ModelVersionRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=MODEL_VERSION_TABLE,
                where_sql="model_name = ? AND version_hash = ?",
                params=[record.model_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, MODEL_VERSION_TABLE)} "
                "WHERE model_name = ? AND version_hash = ?",
                [record.model_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, MODEL_VERSION_TABLE)} "
                "(model_name, version_hash, definition_identity_hash, "
                "identity_metadata_hash, definition_text_b64, identity_metadata_json_b64, "
                "compiled_sql_b64, status, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
                "COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
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
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_model_version(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> ModelVersionRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT model_name, version_hash, definition_identity_hash, "
            "identity_metadata_hash, definition_text_b64, identity_metadata_json_b64, "
            "compiled_sql_b64, status "
            f"FROM {self._qualified_name(schema, MODEL_VERSION_TABLE)} "
            "WHERE model_name = ? AND version_hash = ?",
            [model_name, version_hash],
        ).fetchone()
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
        self, connection: Any, *, schema: str, record: FunctionVersionRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=FUNCTION_VERSION_TABLE,
                where_sql="function_name = ? AND version_hash = ?",
                params=[record.function_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, FUNCTION_VERSION_TABLE)} "
                "WHERE function_name = ? AND version_hash = ?",
                [record.function_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, FUNCTION_VERSION_TABLE)} "
                "(function_name, version_hash, language, returns, arguments_json_b64, "
                "return_columns_json_b64, packages_json_b64, runtime_version, entry_point, "
                "body_sql_b64, definition_text_b64, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
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
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_function_version(
        self, connection: Any, *, schema: str, function_name: str, version_hash: str
    ) -> FunctionVersionRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT function_name, version_hash, language, returns, arguments_json_b64, "
            "return_columns_json_b64, packages_json_b64, runtime_version, entry_point, "
            "body_sql_b64, definition_text_b64, status "
            f"FROM {self._qualified_name(schema, FUNCTION_VERSION_TABLE)} "
            "WHERE function_name = ? AND version_hash = ?",
            [function_name, version_hash],
        ).fetchone()
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
        self, connection: Any, *, schema: str, record: SeedVersionRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=SEED_VERSION_TABLE,
                where_sql="seed_name = ? AND version_hash = ?",
                params=[record.seed_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, SEED_VERSION_TABLE)} "
                "WHERE seed_name = ? AND version_hash = ?",
                [record.seed_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, SEED_VERSION_TABLE)} "
                "(seed_name, version_hash, identity_metadata_hash, "
                "identity_metadata_json_b64, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                [
                    record.seed_name,
                    record.version_hash,
                    record.identity_metadata_hash,
                    record.identity_metadata_json_b64,
                    record.status.value,
                    existing_created_at,
                ],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_seed_version(
        self, connection: Any, *, schema: str, seed_name: str, version_hash: str
    ) -> SeedVersionRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT seed_name, version_hash, identity_metadata_hash, "
            "identity_metadata_json_b64, status "
            f"FROM {self._qualified_name(schema, SEED_VERSION_TABLE)} "
            "WHERE seed_name = ? AND version_hash = ?",
            [seed_name, version_hash],
        ).fetchone()
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
        self, connection: Any, *, schema: str, record: PythonNodeVersionRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=PYTHON_NODE_VERSION_TABLE,
                where_sql="node_type = ? AND node_name = ? AND version_hash = ?",
                params=[record.node_type, record.node_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, PYTHON_NODE_VERSION_TABLE)} "
                "WHERE node_type = ? AND node_name = ? AND version_hash = ?",
                [record.node_type, record.node_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, PYTHON_NODE_VERSION_TABLE)} "
                "(node_type, node_name, version_hash, definition_hash, "
                "identity_metadata_hash, definition_json_b64, identity_metadata_json_b64, "
                "status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), "
                "CURRENT_TIMESTAMP)",
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
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_python_node_version(
        self,
        connection: Any,
        *,
        schema: str,
        node_type: str,
        node_name: str,
        version_hash: str,
    ) -> PythonNodeVersionRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT node_type, node_name, version_hash, definition_hash, "
            "identity_metadata_hash, definition_json_b64, identity_metadata_json_b64, status "
            f"FROM {self._qualified_name(schema, PYTHON_NODE_VERSION_TABLE)} "
            "WHERE node_type = ? AND node_name = ? AND version_hash = ?",
            [node_type, node_name, version_hash],
        ).fetchone()
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
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        record: NodeResultRecord,
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema, NODE_RESULTS_TABLE)} "
            "(virtual_environment_name, node_type, node_name, target_database, target_schema, "
            "target_name, run_id, status, payload_json_b64, metadata_json_b64, error_message, "
            "materialized, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    record.payload, label="payload", node_name=record.node_name
                ),
                encode_node_result_json(
                    record.metadata, label="metadata", node_name=record.node_name
                ),
                record.error_message,
                self._materialized_storage(record.materialized),
                record.ts,
            ],
        )

    def read_node_results(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        node_name: str,
        target_database: str | None,
        target_schema: str | None,
        target_name: str | None,
        statuses: tuple[str, ...] | None,
        run_id: str | None,
        limit: int,
    ) -> tuple[NodeResultEnvelope, ...]:
        if limit < 1:
            return ()
        predicates: list[str] = [
            "virtual_environment_name = ?",
            "node_type = ?",
            "node_name = ?",
            self._optional_equality_sql("target_database", target_database, "?"),
            self._optional_equality_sql("target_schema", target_schema, "?"),
            self._optional_equality_sql("target_name", target_name, "?"),
        ]
        params: list[object] = [virtual_environment_name, node_type, node_name]
        for value in (target_database, target_schema, target_name):
            if value is not None:
                params.append(value)
        if statuses is not None:
            placeholders: str = ", ".join("?" for _ in statuses)
            predicates.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if run_id is not None:
            predicates.append("run_id = ?")
            params.append(run_id)
        params.append(limit)
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT node_type, node_name, run_id, status, payload_json_b64, metadata_json_b64, "
            "error_message, materialized, created_at "
            f"FROM {self._qualified_name(schema, NODE_RESULTS_TABLE)} "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY created_at DESC, run_id DESC LIMIT ?",
            params,
        ).fetchall()
        return tuple(self._node_result_row_to_envelope(row) for row in rows)

    def upsert_physical_relation(
        self, connection: Any, *, schema: str, record: PhysicalRelationRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=PHYSICAL_RELATION_TABLE,
                where_sql="artifact_type = ? AND artifact_name = ? AND version_hash = ?",
                params=[record.artifact_type.value, record.artifact_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
                "WHERE artifact_type = ? AND artifact_name = ? AND version_hash = ?",
                [record.artifact_type.value, record.artifact_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
                "(artifact_type, artifact_name, version_hash, database_name, schema_name, "
                "relation_name, relation_type, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
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
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_physical_relation_for_artifact(
        self,
        connection: Any,
        *,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
        version_hash: str,
    ) -> PhysicalRelationRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT artifact_type, artifact_name, version_hash, database_name, schema_name, "
            "relation_name, relation_type "
            f"FROM {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
            "WHERE artifact_type = ? AND artifact_name = ? AND version_hash = ?",
            [artifact_type.value, artifact_name, version_hash],
        ).fetchone()
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
        connection: Any,
        *,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
    ) -> tuple[PhysicalRelationRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT artifact_type, artifact_name, version_hash, database_name, schema_name, "
            "relation_name, relation_type "
            f"FROM {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
            "WHERE artifact_type = ? AND artifact_name = ? "
            "ORDER BY updated_at DESC, version_hash DESC",
            [artifact_type.value, artifact_name],
        ).fetchall()
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
        self, connection: Any, *, schema: str, record: PhysicalRelationAncestryRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=PHYSICAL_RELATION_ANCESTRY_TABLE,
                where_sql="model_name = ? AND version_hash = ?",
                params=[record.model_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, PHYSICAL_RELATION_ANCESTRY_TABLE)} "
                "WHERE model_name = ? AND version_hash = ?",
                [record.model_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, PHYSICAL_RELATION_ANCESTRY_TABLE)} "
                "(model_name, version_hash, parent_model_name, parent_version_hash, "
                "seed_strategy, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                [
                    record.model_name,
                    record.version_hash,
                    record.parent_model_name,
                    record.parent_version_hash,
                    record.seed_strategy,
                    existing_created_at,
                ],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_physical_relation_ancestry(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationAncestryRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT model_name, version_hash, parent_model_name, parent_version_hash, "
            "seed_strategy "
            f"FROM {self._qualified_name(schema, PHYSICAL_RELATION_ANCESTRY_TABLE)} "
            "WHERE model_name = ? AND version_hash = ?",
            [model_name, version_hash],
        ).fetchone()
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
        self, connection: Any, *, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            self._upsert_virtual_environment_record(connection, schema=schema, record=record)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> VirtualEnvironmentRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT virtual_environment_name, status, baseline_virtual_environment_name, "
            "finalized_at "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_TABLE)} "
            "WHERE virtual_environment_name = ?",
            [virtual_environment_name],
        ).fetchone()
        if row is None:
            return None
        return VirtualEnvironmentRecord(
            virtual_environment_name=row[0],
            status=VirtualEnvironmentStatus(row[1]),
            baseline_virtual_environment_name=row[2],
            finalized_at=row[3],
        )

    def list_virtual_environments(
        self, connection: Any, *, schema: str
    ) -> tuple[VirtualEnvironmentRetentionRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT virtual_environment_name, status, updated_at "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_TABLE)} "
            "ORDER BY updated_at DESC, virtual_environment_name DESC"
        ).fetchall()
        return tuple(
            VirtualEnvironmentRetentionRecord(
                virtual_environment_name=row[0],
                status=VirtualEnvironmentStatus(row[1]),
                updated_at=row[2],
            )
            for row in rows
        )

    def delete_virtual_environment(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = ?",
                [virtual_environment_name],
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema, SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
                "WHERE virtual_environment_name = ?",
                [virtual_environment_name],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_TABLE)} "
                "WHERE virtual_environment_name = ?",
                [virtual_environment_name],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def replace_virtual_environment_node_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_ref_groups(
            connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            refs_by_node_type={node_type: refs},
        )

    def replace_virtual_environment_node_ref_groups(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        connection.execute("BEGIN")
        try:
            self._replace_virtual_environment_node_ref_groups(
                connection,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                refs_by_node_type=refs_by_node_type,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def upsert_virtual_environment_and_replace_node_ref_groups(
        self,
        connection: Any,
        *,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        connection.execute("BEGIN")
        try:
            self._upsert_virtual_environment_record(connection, schema=schema, record=record)
            self._replace_virtual_environment_node_ref_groups(
                connection,
                schema=schema,
                virtual_environment_name=record.virtual_environment_name,
                refs_by_node_type=refs_by_node_type,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_virtual_environment_node_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        node_type: str,
    ) -> tuple[VirtualEnvironmentNodeRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT virtual_environment_name, node_type, node_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            "WHERE virtual_environment_name = ? AND node_type = ? ORDER BY node_name",
            [virtual_environment_name, node_type],
        ).fetchall()
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
        connection: Any,
        *,
        schema: str,
        ref: VirtualEnvironmentNodeRefRecord,
    ) -> None:
        connection.execute(
            "INSERT INTO "
            f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            "(virtual_environment_name, node_type, node_name, version_hash, updated_at) "
            "VALUES (?, ?, ?, ?, now()) "
            "ON CONFLICT (virtual_environment_name, node_type, node_name) "
            "DO UPDATE SET version_hash = excluded.version_hash, updated_at = now()",
            [ref.virtual_environment_name, ref.node_type, ref.node_name, ref.version_hash],
        )

    def replace_virtual_environment_model_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_refs(
            connection,
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
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentModelRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = self.get_virtual_environment_node_refs(
            connection,
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
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        ref: VirtualEnvironmentFunctionRefRecord
        for ref in refs:
            if ref.node_type not in {"udf", "table_fn"}:
                raise StateBackendConfigError("Function ref node_type must be 'udf' or 'table_fn'")
        self.replace_virtual_environment_node_ref_groups(
            connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
            refs_by_node_type={
                node_type: tuple(
                    VirtualEnvironmentNodeRefRecord(
                        virtual_environment_name=ref.virtual_environment_name,
                        node_type=ref.node_type,
                        node_name=ref.function_name,
                        version_hash=ref.version_hash,
                    )
                    for ref in refs
                    if ref.node_type == node_type
                )
                for node_type in ("udf", "table_fn")
            },
        )

    def get_virtual_environment_function_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = (
            *self.get_virtual_environment_node_refs(
                connection,
                schema=schema,
                virtual_environment_name=virtual_environment_name,
                node_type="udf",
            ),
            *self.get_virtual_environment_node_refs(
                connection,
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
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentSeedRefRecord, ...],
    ) -> None:
        self.replace_virtual_environment_node_refs(
            connection,
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
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentSeedRefRecord, ...]:
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...] = self.get_virtual_environment_node_refs(
            connection,
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
        connection: Any,
        *,
        schema: str,
        ref: VirtualEnvironmentPythonNodeRefRecord,
    ) -> None:
        self.upsert_virtual_environment_node_ref(
            connection,
            schema=schema,
            ref=VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.node_name,
                version_hash=ref.version_hash,
            ),
        )

    def get_virtual_environment_python_node_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentPythonNodeRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT virtual_environment_name, node_type, node_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            "WHERE virtual_environment_name = ? "
            "AND node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
            "ORDER BY node_type, node_name",
            [virtual_environment_name],
        ).fetchall()
        return tuple(
            VirtualEnvironmentPythonNodeRefRecord(
                virtual_environment_name=row[0],
                node_type=row[1],
                node_name=row[2],
                version_hash=row[3],
            )
            for row in rows
        )

    def count_unreferenced_python_node_versions(self, connection: Any, *, schema: str) -> int:
        row: tuple[Any, ...] = connection.execute(
            "SELECT COUNT(*) "
            f"FROM {self._qualified_name(schema, PYTHON_NODE_VERSION_TABLE)} versions "
            "WHERE NOT EXISTS ("
            "SELECT 1 "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} refs "
            "WHERE refs.node_type = versions.node_type "
            "AND refs.node_name = versions.node_name "
            "AND refs.version_hash = versions.version_hash)"
        ).fetchone()
        return int(row[0])

    def prune_unreferenced_python_node_versions(self, connection: Any, *, schema: str) -> int:
        before_count: int = self.count_unreferenced_python_node_versions(connection, schema=schema)
        connection.execute(
            f"DELETE FROM {self._qualified_name(schema, PYTHON_NODE_VERSION_TABLE)} versions "
            "WHERE NOT EXISTS ("
            "SELECT 1 "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} refs "
            "WHERE refs.node_type = versions.node_type "
            "AND refs.node_name = versions.node_name "
            "AND refs.version_hash = versions.version_hash)"
        )
        return before_count

    def replace_virtual_environment_source_freshness(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        records: tuple[SourceFreshnessRecord, ...],
    ) -> None:
        self._validate_source_freshness_records(
            virtual_environment_name=virtual_environment_name,
            records=records,
        )
        temp_table_name: str = "__sqlbuild_replace_source_freshness"
        connection.execute("BEGIN")
        try:
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute(
                f"CREATE TEMP TABLE {temp_table_name} ("
                "virtual_environment_name TEXT NOT NULL, "
                "source_name TEXT NOT NULL, "
                "strategy TEXT NOT NULL, "
                "value_kind TEXT NOT NULL, "
                "data_version TEXT NOT NULL, "
                "data_version_hash TEXT NOT NULL, "
                "observed_at TIMESTAMP NOT NULL, "
                "UNIQUE (virtual_environment_name, source_name))"
            )
            record: SourceFreshnessRecord
            for record in records:
                connection.execute(
                    f"INSERT INTO {temp_table_name} "
                    "(virtual_environment_name, source_name, strategy, value_kind, "
                    "data_version, data_version_hash, observed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
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
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
                "WHERE virtual_environment_name = ? "
                f"AND source_name NOT IN (SELECT source_name FROM {temp_table_name})",
                [virtual_environment_name],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
                "(virtual_environment_name, source_name, strategy, value_kind, data_version, "
                "data_version_hash, observed_at, updated_at) "
                "SELECT virtual_environment_name, source_name, strategy, value_kind, "
                f"data_version, data_version_hash, observed_at, now() FROM {temp_table_name} "
                "ON CONFLICT (virtual_environment_name, source_name) "
                "DO UPDATE SET "
                "strategy = excluded.strategy, "
                "value_kind = excluded.value_kind, "
                "data_version = excluded.data_version, "
                "data_version_hash = excluded.data_version_hash, "
                "observed_at = excluded.observed_at, "
                "updated_at = now()"
            )
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_virtual_environment_source_freshness(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[SourceFreshnessRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT virtual_environment_name, source_name, strategy, value_kind, "
            "data_version, data_version_hash, observed_at "
            f"FROM {self._qualified_name(schema, SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
            "WHERE virtual_environment_name = ? ORDER BY source_name",
            [virtual_environment_name],
        ).fetchall()
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
        connection: Any,
        *,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
        seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (),
    ) -> None:
        connection.execute("BEGIN")
        try:
            checkpoint_model_ref_table: str = self._qualified_name(
                schema,
                VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
            )
            checkpoint_seed_ref_table: str = self._qualified_name(
                schema,
                VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE)} "
                "(checkpoint_id, virtual_environment_name, created_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                [checkpoint.checkpoint_id, checkpoint.virtual_environment_name],
            )
            for ref in refs:
                connection.execute(
                    "INSERT INTO "
                    f"{checkpoint_model_ref_table} "
                    "(checkpoint_id, model_name, version_hash) VALUES (?, ?, ?)",
                    [ref.checkpoint_id, ref.model_name, ref.version_hash],
                )
            function_ref: VirtualEnvironmentCheckpointFunctionRefRecord
            for function_ref in function_refs:
                checkpoint_function_ref_table: str = self._qualified_name(
                    schema,
                    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
                )
                connection.execute(
                    "INSERT INTO "
                    f"{checkpoint_function_ref_table} "
                    "(checkpoint_id, function_name, version_hash) VALUES (?, ?, ?)",
                    [
                        function_ref.checkpoint_id,
                        function_ref.function_name,
                        function_ref.version_hash,
                    ],
                )
            seed_ref: VirtualEnvironmentCheckpointSeedRefRecord
            for seed_ref in seed_refs:
                connection.execute(
                    "INSERT INTO "
                    f"{checkpoint_seed_ref_table} "
                    "(checkpoint_id, seed_name, version_hash) VALUES (?, ?, ?)",
                    [seed_ref.checkpoint_id, seed_ref.seed_name, seed_ref.version_hash],
                )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def list_virtual_environment_checkpoints(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentCheckpointRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT checkpoint_id, virtual_environment_name, created_at "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE)} "
            "WHERE virtual_environment_name = ? ORDER BY created_at DESC, checkpoint_id DESC",
            [virtual_environment_name],
        ).fetchall()
        return tuple(
            VirtualEnvironmentCheckpointRecord(
                checkpoint_id=row[0],
                virtual_environment_name=row[1],
                created_at=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_model_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointModelRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            f"SELECT checkpoint_id, model_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE)} "
            "WHERE checkpoint_id = ? ORDER BY model_name",
            [checkpoint_id],
        ).fetchall()
        return tuple(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id=row[0],
                model_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_function_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...]:
        checkpoint_function_ref_table: str = self._qualified_name(
            schema,
            VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
        )
        rows: list[tuple[Any, ...]] = connection.execute(
            f"SELECT checkpoint_id, function_name, version_hash "
            f"FROM {checkpoint_function_ref_table} "
            "WHERE checkpoint_id = ? ORDER BY function_name",
            [checkpoint_id],
        ).fetchall()
        return tuple(
            VirtualEnvironmentCheckpointFunctionRefRecord(
                checkpoint_id=row[0],
                function_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def get_virtual_environment_checkpoint_seed_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            f"SELECT checkpoint_id, seed_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE)} "
            "WHERE checkpoint_id = ? ORDER BY seed_name",
            [checkpoint_id],
        ).fetchall()
        return tuple(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id=row[0],
                seed_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def delete_virtual_environment_checkpoint(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> None:
        connection.execute("BEGIN")
        try:
            checkpoint_function_ref_table: str = self._qualified_name(
                schema,
                VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE)} "
                "WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                f"DELETE FROM {checkpoint_function_ref_table} WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE)} "
                "WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE)} "
                "WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def upsert_state_operation(
        self, connection: Any, *, schema: str, record: StateOperationRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=STATE_OPERATION_TABLE,
                where_sql="operation_id = ?",
                params=[record.operation_id],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, STATE_OPERATION_TABLE)} "
                "WHERE operation_id = ?",
                [record.operation_id],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, STATE_OPERATION_TABLE)} "
                "(operation_id, operation_type, status, virtual_environment_name, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                [
                    record.operation_id,
                    record.operation_type.value,
                    record.status.value,
                    record.virtual_environment_name,
                    existing_created_at,
                ],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_state_operation(
        self, connection: Any, *, schema: str, operation_id: str
    ) -> StateOperationRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT operation_id, operation_type, status, virtual_environment_name "
            f"FROM {self._qualified_name(schema, STATE_OPERATION_TABLE)} "
            "WHERE operation_id = ?",
            [operation_id],
        ).fetchone()
        if row is None:
            return None
        return StateOperationRecord(
            operation_id=row[0],
            operation_type=StateOperationType(row[1]),
            status=StateOperationStatus(row[2]),
            virtual_environment_name=row[3],
        )

    def create_state_operation_event(
        self, connection: Any, *, schema: str, record: StateOperationEventRecord
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema, STATE_OPERATION_EVENT_TABLE)} "
            "(event_id, operation_id, action, status, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [
                record.event_id,
                record.operation_id,
                record.action,
                record.status.value,
                record.message,
            ],
        )

    def create_reconcile_event(
        self, connection: Any, *, schema: str, record: ReconcileEventRecord
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema, RECONCILE_EVENT_TABLE)} "
            "(event_id, action, status, message, created_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [record.event_id, record.action.value, record.status.value, record.message],
        )

    def acquire_lock(
        self,
        connection: Any,
        *,
        schema: str,
        lock_key: str,
        owner_id: str,
        expires_at: datetime,
    ) -> bool:
        connection.execute("BEGIN")
        try:
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, LOCK_TABLE)} "
                "WHERE lock_key = ? AND expires_at <= CURRENT_TIMESTAMP",
                [lock_key],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, LOCK_TABLE)} "
                "(lock_key, owner_id, expires_at, created_at, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                [lock_key, owner_id, expires_at],
            )
            connection.execute("COMMIT")
            return True
        except BaseException:
            try:
                connection.execute("ROLLBACK")
            except BaseException:
                pass
            active_row: tuple[Any, ...] | None = connection.execute(
                f"SELECT owner_id FROM {self._qualified_name(schema, LOCK_TABLE)} "
                "WHERE lock_key = ? AND expires_at > CURRENT_TIMESTAMP",
                [lock_key],
            ).fetchone()
            if active_row is not None:
                return False
            raise

    def release_lock(self, connection: Any, *, schema: str, lock_key: str, owner_id: str) -> bool:
        connection.execute("BEGIN")
        try:
            existing_row: tuple[Any, ...] | None = connection.execute(
                f"SELECT owner_id FROM {self._qualified_name(schema, LOCK_TABLE)} "
                "WHERE lock_key = ? AND owner_id = ?",
                [lock_key, owner_id],
            ).fetchone()
            if existing_row is None:
                connection.execute("COMMIT")
                return False
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, LOCK_TABLE)} "
                "WHERE lock_key = ? AND owner_id = ?",
                [lock_key, owner_id],
            )
            connection.execute("COMMIT")
            return True
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def list_active_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT lock_key, owner_id, expires_at FROM "
            f"{self._qualified_name(schema, LOCK_TABLE)} "
            "WHERE expires_at > CURRENT_TIMESTAMP ORDER BY lock_key"
        ).fetchall()
        return tuple(
            StateLockRecord(lock_key=row[0], owner_id=row[1], expires_at=row[2]) for row in rows
        )

    def list_expired_locks(self, connection: Any, *, schema: str) -> tuple[StateLockRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT lock_key, owner_id, expires_at FROM "
            f"{self._qualified_name(schema, LOCK_TABLE)} "
            "WHERE expires_at <= CURRENT_TIMESTAMP ORDER BY lock_key"
        ).fetchall()
        return tuple(
            StateLockRecord(lock_key=row[0], owner_id=row[1], expires_at=row[2]) for row in rows
        )

    def delete_lock(self, connection: Any, *, schema: str, lock_key: str) -> None:
        connection.execute(
            f"DELETE FROM {self._qualified_name(schema, LOCK_TABLE)} WHERE lock_key = ?",
            [lock_key],
        )

    def list_state_backups(self, connection: Any, *, schema: str) -> tuple[StateBackupRecord, ...]:
        prefix: str = f"{schema}__backup_%"
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT s.schema_name, e.backup_id, MAX(e.created_at) "
            "FROM information_schema.schemata s "
            f"LEFT JOIN {self._qualified_name(schema, STATE_MIGRATION_EVENTS_TABLE)} e "
            "ON s.schema_name = ? || e.backup_id "
            "WHERE s.schema_name LIKE ? "
            "GROUP BY s.schema_name, e.backup_id ORDER BY s.schema_name DESC",
            [f"{schema}__backup_", prefix],
        ).fetchall()
        return tuple(
            StateBackupRecord(
                backup_id=row[1] or str(row[0]).removeprefix(f"{schema}__backup_"),
                schema_name=row[0],
                created_at=row[2],
            )
            for row in rows
        )

    def delete_state_backup(self, connection: Any, *, schema: str, backup_id: str) -> None:
        backup_schema: str = self._backup_schema_name(schema=schema, backup_id_value=backup_id)
        connection.execute(f"DROP SCHEMA IF EXISTS {self._quote_identifier(backup_schema)} CASCADE")

    def _latest_backup_id(self, connection: Any, *, schema: str) -> str:
        prefix: str = f"{schema}__backup_%"
        rows: list[tuple[str]] = connection.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE ? "
            "ORDER BY schema_name DESC LIMIT 1",
            [prefix],
        ).fetchall()
        if not rows:
            raise StateBackupNotFoundError("No state backup is available for rollback")
        return rows[0][0].removeprefix(f"{schema}__backup_")

    def _schema_exists(self, connection: Any, *, schema: str) -> bool:
        rows: list[tuple[str]] = connection.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ?",
            [schema],
        ).fetchall()
        return bool(rows)

    def _record_event(
        self,
        connection: Any,
        *,
        schema: str,
        action: StateMigrationAction,
        backup_id_value: str | None,
        status: StateMigrationStatus,
        message: str | None,
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema, STATE_MIGRATION_EVENTS_TABLE)} "
            "(event_id, action, backup_id, status, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [event_id(), action.value, backup_id_value, status.value, message],
        )

    def _created_at_for_key(
        self,
        connection: Any,
        *,
        schema: str,
        table_name: str,
        where_sql: str,
        params: list[object],
    ) -> datetime | None:
        row: tuple[Any, ...] | None = connection.execute(
            f"SELECT created_at FROM {self._qualified_name(schema, table_name)} WHERE {where_sql}",
            params,
        ).fetchone()
        if row is None:
            return None
        return row[0]

    def _create_additional_state_tables(self, connection: Any, *, schema: str) -> None:
        table_name: str
        columns: dict[str, StateColumnType]
        for table_name, columns in STATE_TABLE_COLUMNS.items():
            if table_name in {STATE_VERSION_TABLE, STATE_MIGRATION_EVENTS_TABLE}:
                continue
            column_sql: str = ", ".join(
                f"{self._quote_identifier(column_name)} {self._state_column_sql_type(column_type)}"
                for column_name, column_type in columns.items()
            )
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {self._qualified_name(schema, table_name)} "
                f"({column_sql})"
            )
            column_name: str
            column_type: StateColumnType
            for column_name, column_type in columns.items():
                connection.execute(
                    f"ALTER TABLE {self._qualified_name(schema, table_name)} "
                    f"ADD COLUMN IF NOT EXISTS {self._quote_identifier(column_name)} "
                    f"{self._state_column_sql_type(column_type)}"
                )
        self._create_state_indexes(connection, schema=schema)

    def _create_state_indexes(self, connection: Any, *, schema: str) -> None:
        table_name: str
        indexes: dict[str, tuple[str, ...]]
        for table_name, indexes in STATE_TABLE_INDEXES.items():
            index_name: str
            columns: tuple[str, ...]
            for index_name, columns in indexes.items():
                column_sql: str = ", ".join(self._quote_identifier(column) for column in columns)
                connection.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {self._quote_identifier(index_name)} "
                    f"ON {self._qualified_name(schema, table_name)} ({column_sql})"
                )

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
            str(row[5]), label="metadata", node_name=node_name
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
            payload=decode_node_result_json(str(row[4]), label="payload", node_name=node_name),
            metadata=normalized_metadata,
            error_message=str(row[6]) if row[6] is not None else None,
            materialized=self._parse_materialized(row[7]),
            ts=row[8],
        )

    def _optional_equality_sql(self, column: str, value: object | None, placeholder: str) -> str:
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
        return str(value).lower() == "true"

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _qualified_name(self, schema: str, table: str) -> str:
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
        self, connection: Any, *, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        existing_created_at: datetime | None = self._created_at_for_key(
            connection,
            schema=schema,
            table_name=VIRTUAL_ENVIRONMENT_TABLE,
            where_sql="virtual_environment_name = ?",
            params=[record.virtual_environment_name],
        )
        connection.execute(
            f"DELETE FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_TABLE)} "
            "WHERE virtual_environment_name = ?",
            [record.virtual_environment_name],
        )
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_TABLE)} "
            "(virtual_environment_name, status, baseline_virtual_environment_name, "
            "created_at, updated_at, finalized_at) "
            "VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP, ?)",
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
        connection: Any,
        *,
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
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = ? AND node_type = ?",
                [virtual_environment_name, node_type],
            )
            ref: VirtualEnvironmentNodeRefRecord
            for ref in refs:
                connection.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                    "(virtual_environment_name, node_type, node_name, version_hash, updated_at) "
                    "VALUES (?, ?, ?, ?, now()) "
                    "ON CONFLICT (virtual_environment_name, node_type, node_name) "
                    "DO UPDATE SET version_hash = excluded.version_hash, updated_at = now()",
                    [
                        ref.virtual_environment_name,
                        ref.node_type,
                        ref.node_name,
                        ref.version_hash,
                    ],
                )

    def _backup_schema_name(self, *, schema: str, backup_id_value: str) -> str:
        return f"{schema}__backup_{backup_id_value}"

    def _state_type_matches(self, actual_type: str, expected_type: StateColumnType) -> bool:
        actual: str = actual_type.lower()
        match expected_type:
            case StateColumnType.INTEGER:
                return "int" in actual
            case StateColumnType.TEXT:
                return any(token in actual for token in ("text", "varchar", "character", "string"))
            case StateColumnType.TIMESTAMP:
                return "timestamp" in actual or "datetime" in actual
        return False
