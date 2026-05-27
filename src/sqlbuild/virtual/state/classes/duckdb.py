"""DuckDB virtual-state backend."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.constants import (
    CURRENT_STATE_SCHEMA_VERSION,
    FUNCTION_VERSION_TABLE,
    LOCK_TABLE,
    MODEL_VERSION_TABLE,
    PHYSICAL_RELATION_TABLE,
    STATE_MIGRATION_EVENTS_TABLE,
    STATE_TABLE_COLUMNS,
    STATE_TABLE_INDEXES,
    STATE_TABLES,
    STATE_VERSION_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_REF_TABLE,
    VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE,
    VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE,
    VIRTUAL_ENVIRONMENT_REF_TABLE,
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
    PhysicalRelationRecord,
    StateLockRecord,
    StateSchemaValidationResult,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    StateColumnType,
    StateMigrationAction,
    StateMigrationStatus,
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
                "(model_name, version_hash, data_hash, metadata_hash, "
                "fingerprint_query_sql_b64, fingerprint_metadata_json_b64, "
                "compiled_sql_b64, status, "
                "created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
                "COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                [
                    record.model_name,
                    record.version_hash,
                    record.data_hash,
                    record.metadata_hash,
                    record.fingerprint_query_sql_b64,
                    record.fingerprint_metadata_json_b64,
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
            "SELECT model_name, version_hash, data_hash, metadata_hash, "
            "fingerprint_query_sql_b64, fingerprint_metadata_json_b64, "
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
            data_hash=row[2],
            metadata_hash=row[3],
            fingerprint_query_sql_b64=row[4],
            fingerprint_metadata_json_b64=row[5],
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
                "body_sql_b64, fingerprint_query_sql_b64, status, created_at, updated_at) "
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
                    record.fingerprint_query_sql_b64,
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
            "body_sql_b64, fingerprint_query_sql_b64, status "
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
            fingerprint_query_sql_b64=row[10],
            status=ModelVersionStatus(row[11]),
        )

    def upsert_physical_relation(
        self, connection: Any, *, schema: str, record: PhysicalRelationRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
            existing_created_at: datetime | None = self._created_at_for_key(
                connection,
                schema=schema,
                table_name=PHYSICAL_RELATION_TABLE,
                where_sql="model_name = ? AND version_hash = ?",
                params=[record.model_name, record.version_hash],
            )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
                "WHERE model_name = ? AND version_hash = ?",
                [record.model_name, record.version_hash],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
                "(model_name, version_hash, database_name, schema_name, relation_name, "
                "relation_type, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)",
                [
                    record.model_name,
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

    def get_physical_relation(
        self, connection: Any, *, schema: str, model_name: str, version_hash: str
    ) -> PhysicalRelationRecord | None:
        row: tuple[Any, ...] | None = connection.execute(
            "SELECT model_name, version_hash, database_name, schema_name, "
            "relation_name, relation_type "
            f"FROM {self._qualified_name(schema, PHYSICAL_RELATION_TABLE)} "
            "WHERE model_name = ? AND version_hash = ?",
            [model_name, version_hash],
        ).fetchone()
        if row is None:
            return None
        return PhysicalRelationRecord(
            model_name=row[0],
            version_hash=row[1],
            database_name=row[2],
            schema_name=row[3],
            relation_name=row[4],
            relation_type=row[5],
        )

    def upsert_virtual_environment(
        self, connection: Any, *, schema: str, record: VirtualEnvironmentRecord
    ) -> None:
        connection.execute("BEGIN")
        try:
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

    def replace_virtual_environment_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentRefRecord, ...],
    ) -> None:
        temp_table_name: str = "__sqlbuild_replace_virtual_environment_refs"
        connection.execute("BEGIN")
        try:
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute(
                f"CREATE TEMP TABLE {temp_table_name} ("
                "virtual_environment_name TEXT NOT NULL, "
                "model_name TEXT NOT NULL, "
                "version_hash TEXT NOT NULL, "
                "UNIQUE (virtual_environment_name, model_name))"
            )
            for ref in refs:
                connection.execute(
                    f"INSERT INTO {temp_table_name} "
                    "(virtual_environment_name, model_name, version_hash) "
                    "VALUES (?, ?, ?)",
                    [ref.virtual_environment_name, ref.model_name, ref.version_hash],
                )
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_REF_TABLE)} "
                "WHERE virtual_environment_name = ? "
                f"AND model_name NOT IN (SELECT model_name FROM {temp_table_name})",
                [virtual_environment_name],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_REF_TABLE)} "
                "(virtual_environment_name, model_name, version_hash, updated_at) "
                "SELECT virtual_environment_name, model_name, version_hash, now() "
                f"FROM {temp_table_name} "
                "ON CONFLICT (virtual_environment_name, model_name) "
                "DO UPDATE SET "
                "version_hash = excluded.version_hash, "
                "updated_at = now()"
            )
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_virtual_environment_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            f"SELECT virtual_environment_name, model_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_REF_TABLE)} "
            "WHERE virtual_environment_name = ? ORDER BY model_name",
            [virtual_environment_name],
        ).fetchall()
        return tuple(
            VirtualEnvironmentRefRecord(
                virtual_environment_name=row[0],
                model_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def replace_virtual_environment_function_refs(
        self,
        connection: Any,
        *,
        schema: str,
        virtual_environment_name: str,
        refs: tuple[VirtualEnvironmentFunctionRefRecord, ...],
    ) -> None:
        temp_table_name: str = "__sqlbuild_replace_virtual_environment_function_refs"
        connection.execute("BEGIN")
        try:
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute(
                f"CREATE TEMP TABLE {temp_table_name} ("
                "virtual_environment_name TEXT NOT NULL, "
                "function_name TEXT NOT NULL, "
                "version_hash TEXT NOT NULL, "
                "UNIQUE (virtual_environment_name, function_name))"
            )
            ref: VirtualEnvironmentFunctionRefRecord
            for ref in refs:
                connection.execute(
                    f"INSERT INTO {temp_table_name} "
                    "(virtual_environment_name, function_name, version_hash) "
                    "VALUES (?, ?, ?)",
                    [ref.virtual_environment_name, ref.function_name, ref.version_hash],
                )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE)} "
                "WHERE virtual_environment_name = ? "
                f"AND function_name NOT IN (SELECT function_name FROM {temp_table_name})",
                [virtual_environment_name],
            )
            connection.execute(
                "INSERT INTO "
                f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE)} "
                "(virtual_environment_name, function_name, version_hash, updated_at) "
                "SELECT virtual_environment_name, function_name, version_hash, now() "
                f"FROM {temp_table_name} "
                "ON CONFLICT (virtual_environment_name, function_name) "
                "DO UPDATE SET "
                "version_hash = excluded.version_hash, "
                "updated_at = now()"
            )
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def get_virtual_environment_function_refs(
        self, connection: Any, *, schema: str, virtual_environment_name: str
    ) -> tuple[VirtualEnvironmentFunctionRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT virtual_environment_name, function_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_FUNCTION_REF_TABLE)} "
            "WHERE virtual_environment_name = ? ORDER BY function_name",
            [virtual_environment_name],
        ).fetchall()
        return tuple(
            VirtualEnvironmentFunctionRefRecord(
                virtual_environment_name=row[0],
                function_name=row[1],
                version_hash=row[2],
            )
            for row in rows
        )

    def create_virtual_environment_checkpoint(
        self,
        connection: Any,
        *,
        schema: str,
        checkpoint: VirtualEnvironmentCheckpointRecord,
        refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
        function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (),
    ) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE)} "
                "(checkpoint_id, virtual_environment_name, created_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                [checkpoint.checkpoint_id, checkpoint.virtual_environment_name],
            )
            for ref in refs:
                connection.execute(
                    "INSERT INTO "
                    f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_REF_TABLE)} "
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

    def get_virtual_environment_checkpoint_refs(
        self, connection: Any, *, schema: str, checkpoint_id: str
    ) -> tuple[VirtualEnvironmentCheckpointRefRecord, ...]:
        rows: list[tuple[Any, ...]] = connection.execute(
            f"SELECT checkpoint_id, model_name, version_hash "
            f"FROM {self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_REF_TABLE)} "
            "WHERE checkpoint_id = ? ORDER BY model_name",
            [checkpoint_id],
        ).fetchall()
        return tuple(
            VirtualEnvironmentCheckpointRefRecord(
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
                f"DELETE FROM {checkpoint_function_ref_table} WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema, VIRTUAL_ENVIRONMENT_CHECKPOINT_REF_TABLE)} "
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

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _qualified_name(self, schema: str, table: str) -> str:
        return f"{self._quote_identifier(schema)}.{self._quote_identifier(table)}"

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
