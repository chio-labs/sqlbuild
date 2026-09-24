"""DuckDB virtual-state backend."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime
from typing import Any, ClassVar

from sqlbuild.adapter.contract.classes.observed_connection import ObservedConnection
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.executor.node_results.main.decode_json import decode_node_result_json
from sqlbuild.executor.node_results.main.encode_json import encode_node_result_json
from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from sqlbuild.virtual.state._helpers.state_storage.datetime import (
    to_naive_utc_wall_clock,
)
from sqlbuild.virtual.state._helpers.state_storage.events import backup_id, event_id
from sqlbuild.virtual.state._helpers.state_storage.microbatch_events import (
    append_duckdb_microbatch_event,
    append_duckdb_microbatch_events,
    read_duckdb_microbatch_model_history,
    read_duckdb_microbatch_retention_history,
    read_duckdb_microbatch_scope_history,
)
from sqlbuild.virtual.state._helpers.state_storage.validation import build_validation_result
from sqlbuild.virtual.state.classes._duckdb_conditional_publish import (
    DuckDbConditionalPublishMixin,
)
from sqlbuild.virtual.state.classes._sql_state_backend import SqlStateBackend
from sqlbuild.virtual.state.constants import (
    CURRENT_STATE_SCHEMA_VERSION,
    DUCKDB_DATETIME_TYPE_TOKEN,
    DUCKDB_INTEGER_TYPE_TOKEN,
    DUCKDB_TIMESTAMP_TYPE_TOKEN,
    LOCK_TABLE,
    MICROBATCH_EVENT_TABLE,
    NODE_RESULTS_TABLE,
    NON_UNIQUE_STATE_INDEXES,
    PYTHON_NODE_VERSION_TABLE,
    RECONCILE_EVENT_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_BOOLEAN_TRUE,
    STATE_MIGRATION_EVENTS_TABLE,
    STATE_OPERATION_EVENT_TABLE,
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
    ReconcileEventRecord,
    SourceFreshnessRecord,
    StateBackupRecord,
    StateOperationEventRecord,
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
    StateColumnType,
    StateMigrationAction,
    StateMigrationStatus,
)


class DuckDbStateBackend(DuckDbConditionalPublishMixin, SqlStateBackend):
    """DuckDB implementation for virtual state."""

    _placeholder: ClassVar[str] = "?"

    def connect(self, config: dict[str, object]) -> Any:
        import duckdb

        database: object | None = config.get("database")
        if not isinstance(database, str) or not database:
            raise StateBackendConfigError("DuckDB state backend requires state.connection.database")
        return ObservedConnection(raw_connection=duckdb.connect(database), adapter="duckdb")

    def close(self, connection: Any) -> None:
        connection.close()

    def _fetch_one(
        self, *, connection: Any, sql: str, params: Sequence[object] | None = None
    ) -> tuple[Any, ...] | None:
        if params is None:
            return connection.execute(sql).fetchone()
        return connection.execute(sql, params).fetchone()

    def _fetch_all(
        self, *, connection: Any, sql: str, params: Sequence[object] | None = None
    ) -> list[tuple[Any, ...]]:
        if params is None:
            return connection.execute(sql).fetchall()
        return connection.execute(sql, params).fetchall()

    @contextmanager
    def _write_transaction(self, *, connection: Any) -> Iterator[Any]:
        connection.execute("BEGIN")
        try:
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def _execute_in(self, *, executor: Any, sql: str, params: Sequence[object]) -> None:
        executor.execute(sql, params)

    def _fetch_one_in(
        self, *, executor: Any, sql: str, params: Sequence[object]
    ) -> tuple[Any, ...] | None:
        return executor.execute(sql, params).fetchone()

    def initialize(self, *, connection: Any, schema: str, sqlbuild_version: str) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS "
                f"{self._qualified_name(schema=schema, table=STATE_VERSION_TABLE)} ("
                "schema_version INTEGER NOT NULL, "
                "sqlbuild_version TEXT NOT NULL, "
                "updated_at TIMESTAMP NOT NULL"
                ")"
            )
            connection.execute(
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
            self._create_additional_state_tables(connection=connection, schema=schema)
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema=schema, table=STATE_VERSION_TABLE)}"
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema=schema, table=STATE_VERSION_TABLE)} "
                "(schema_version, sqlbuild_version, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                [CURRENT_STATE_SCHEMA_VERSION, sqlbuild_version],
            )
            self._record_event(
                connection=connection,
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

    def inspect_schema(self, *, connection: Any, schema: str) -> StateSchemaValidationResult:
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
        connection.execute("BEGIN")
        try:
            connection.execute(f"CREATE SCHEMA {self._quote_identifier(backup_schema)}")
            table_name: str
            for table_name in STATE_TABLES:
                connection.execute(
                    f"CREATE TABLE {self._qualified_name(schema=backup_schema, table=table_name)} "
                    "AS "
                    f"SELECT * FROM {self._qualified_name(schema=schema, table=table_name)}"
                )
            self._record_event(
                connection=connection,
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
        connection.execute("BEGIN")
        try:
            table_name: str
            for table_name in STATE_TABLES:
                connection.execute(
                    f"DROP TABLE IF EXISTS {self._qualified_name(schema=schema, table=table_name)}"
                )
            connection.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
            for table_name in STATE_TABLES:
                connection.execute(
                    f"CREATE TABLE {self._qualified_name(schema=schema, table=table_name)} AS "
                    f"SELECT * FROM {self._qualified_name(schema=backup_schema, table=table_name)}"
                )
            self._create_state_indexes(connection=connection, schema=schema)
            self._record_event(
                connection=connection,
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

    def reset(self, *, connection: Any, schema: str) -> None:
        connection.execute("BEGIN")
        try:
            for table_name in STATE_TABLES:
                connection.execute(
                    f"DROP TABLE IF EXISTS {self._qualified_name(schema=schema, table=table_name)}"
                )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def insert_node_result(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        record: NodeResultRecord,
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema=schema, table=NODE_RESULTS_TABLE)} "
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
            "virtual_environment_name = ?",
            "node_type = ?",
            "node_name = ?",
            self._optional_equality_sql(
                column="target_database", value=query.target_database, placeholder="?"
            ),
            self._optional_equality_sql(
                column="target_schema", value=query.target_schema, placeholder="?"
            ),
            self._optional_equality_sql(
                column="target_name", value=query.target_name, placeholder="?"
            ),
        ]
        params: list[object] = [virtual_environment_name, query.node_type, query.node_name]
        for value in (query.target_database, query.target_schema, query.target_name):
            if value is not None:
                params.append(value)
        if query.statuses is not None:
            placeholders: str = ", ".join("?" for _ in query.statuses)
            predicates.append(f"status IN ({placeholders})")
            params.extend(query.statuses)
        if query.run_id is not None:
            predicates.append("run_id = ?")
            params.append(query.run_id)
        params.append(query.limit)
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT node_type, node_name, run_id, status, payload_json_b64, metadata_json_b64, "
            "error_message, materialized, created_at "
            f"FROM {self._qualified_name(schema=schema, table=NODE_RESULTS_TABLE)} "
            f"WHERE {' AND '.join(predicates)} "
            "ORDER BY created_at DESC, run_id DESC LIMIT ?",
            params,
        ).fetchall()
        return tuple(self._node_result_row_to_envelope(row) for row in rows)

    def append_microbatch_event(
        self, *, connection: Any, schema: str, event: MicrobatchEvent
    ) -> None:
        append_duckdb_microbatch_event(
            connection=connection,
            qualified_table=self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE),
            event=event,
        )

    def append_microbatch_events(
        self, *, connection: Any, schema: str, events: tuple[MicrobatchEvent, ...]
    ) -> MicrobatchWriteResult:
        return append_duckdb_microbatch_events(
            connection=connection,
            qualified_table=self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE),
            events=events,
        )

    def read_microbatch_scope_history(
        self, *, connection: Any, schema: str, scope: MicrobatchScope
    ) -> tuple[MicrobatchEvent, ...]:
        return read_duckdb_microbatch_scope_history(
            connection=connection,
            qualified_table=self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE),
            scope=scope,
        )

    def read_microbatch_retention_history(
        self, *, connection: Any, schema: str
    ) -> tuple[MicrobatchEvent, ...]:
        return read_duckdb_microbatch_retention_history(
            connection=connection,
            qualified_table=self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE),
        )

    def read_microbatch_model_history(
        self, *, connection: Any, schema: str, scope: MicrobatchScope
    ) -> tuple[MicrobatchEvent, ...]:
        return read_duckdb_microbatch_model_history(
            connection=connection,
            qualified_table=self._qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE),
            scope=scope,
        )

    def delete_virtual_environment(
        self, *, connection: Any, schema: str, virtual_environment_name: str
    ) -> None:
        connection.execute("BEGIN")
        try:
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = ?",
                [virtual_environment_name],
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
                "WHERE virtual_environment_name = ?",
                [virtual_environment_name],
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_TABLE)} "
                "WHERE virtual_environment_name = ?",
                [virtual_environment_name],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
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
        connection.execute("BEGIN")
        try:
            self._replace_virtual_environment_node_ref_groups(
                connection=connection,
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
        *,
        connection: Any,
        schema: str,
        record: VirtualEnvironmentRecord,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        connection.execute("BEGIN")
        try:
            self._upsert_virtual_environment_record(
                executor=connection, schema=schema, record=record
            )
            self._replace_virtual_environment_node_ref_groups(
                connection=connection,
                schema=schema,
                virtual_environment_name=record.virtual_environment_name,
                refs_by_node_type=refs_by_node_type,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def upsert_virtual_environment_node_ref(
        self,
        *,
        connection: Any,
        schema: str,
        ref: VirtualEnvironmentNodeRefRecord,
    ) -> None:
        connection.execute(
            "INSERT INTO "
            f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            "(virtual_environment_name, node_type, node_name, version_hash, updated_at) "
            "VALUES (?, ?, ?, ?, now()) "
            "ON CONFLICT (virtual_environment_name, node_type, node_name) "
            "DO UPDATE SET version_hash = excluded.version_hash, updated_at = now()",
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

    def count_unreferenced_python_node_versions(self, *, connection: Any, schema: str) -> int:
        row: tuple[Any, ...] = connection.execute(
            "SELECT COUNT(*) "
            f"FROM {self._qualified_name(schema=schema, table=PYTHON_NODE_VERSION_TABLE)} versions "
            "WHERE NOT EXISTS ("
            "SELECT 1 "
            "FROM "
            f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
            "refs "
            "WHERE refs.node_type = versions.node_type "
            "AND refs.node_name = versions.node_name "
            "AND refs.version_hash = versions.version_hash)"
        ).fetchone()
        return int(row[0])

    def prune_unreferenced_python_node_versions(self, *, connection: Any, schema: str) -> int:
        before_count: int = self.count_unreferenced_python_node_versions(
            connection=connection, schema=schema
        )
        connection.execute(
            "DELETE FROM "
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
                        to_naive_utc_wall_clock(record.observed_at),
                    ],
                )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
                "WHERE virtual_environment_name = ? "
                f"AND source_name NOT IN (SELECT source_name FROM {temp_table_name})",
                [virtual_environment_name],
            )
            connection.execute(
                "INSERT INTO "
                f"{self._qualified_name(schema=schema, table=SOURCE_FRESHNESS_OBSERVATION_TABLE)} "
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
        connection.execute("BEGIN")
        try:
            self._insert_virtual_environment_checkpoint_rows(
                connection=connection,
                schema=schema,
                checkpoint=checkpoint,
                refs=refs,
                function_refs=function_refs,
                seed_refs=seed_refs,
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def delete_virtual_environment_checkpoint(
        self, *, connection: Any, schema: str, checkpoint_id: str
    ) -> None:
        connection.execute("BEGIN")
        try:
            checkpoint_function_ref_table: str = self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_FUNCTION_REF_TABLE,
            )
            checkpoint_seed_ref_table: str = self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_SEED_REF_TABLE,
            )
            checkpoint_model_ref_table: str = self._qualified_name(
                schema=schema,
                table=VIRTUAL_ENVIRONMENT_CHECKPOINT_MODEL_REF_TABLE,
            )
            connection.execute(
                f"DELETE FROM {checkpoint_seed_ref_table} WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                f"DELETE FROM {checkpoint_function_ref_table} WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                f"DELETE FROM {checkpoint_model_ref_table} WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_CHECKPOINT_TABLE)}"
                " "
                "WHERE checkpoint_id = ?",
                [checkpoint_id],
            )
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def create_state_operation_event(
        self, *, connection: Any, schema: str, record: StateOperationEventRecord
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema=schema, table=STATE_OPERATION_EVENT_TABLE)} "
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
        self, *, connection: Any, schema: str, record: ReconcileEventRecord
    ) -> None:
        connection.execute(
            f"INSERT INTO {self._qualified_name(schema=schema, table=RECONCILE_EVENT_TABLE)} "
            "(event_id, action, status, message, created_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
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
        connection.execute("BEGIN")
        try:
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "WHERE lock_key = ? AND expires_at <= CURRENT_TIMESTAMP",
                [lock_key],
            )
            connection.execute(
                f"INSERT INTO {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
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
                f"SELECT owner_id FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "WHERE lock_key = ? AND expires_at > CURRENT_TIMESTAMP",
                [lock_key],
            ).fetchone()
            if active_row is not None:
                return False
            raise

    def release_lock(self, *, connection: Any, schema: str, lock_key: str, owner_id: str) -> bool:
        connection.execute("BEGIN")
        try:
            existing_row: tuple[Any, ...] | None = connection.execute(
                f"SELECT owner_id FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "WHERE lock_key = ? AND owner_id = ?",
                [lock_key, owner_id],
            ).fetchone()
            if existing_row is None:
                connection.execute("COMMIT")
                return False
            connection.execute(
                f"DELETE FROM {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
                "WHERE lock_key = ? AND owner_id = ?",
                [lock_key, owner_id],
            )
            connection.execute("COMMIT")
            return True
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def delete_lock(self, *, connection: Any, schema: str, lock_key: str) -> None:
        connection.execute(
            "DELETE FROM "
            f"{self._qualified_name(schema=schema, table=LOCK_TABLE)} WHERE lock_key = ?",
            [lock_key],
        )

    def list_state_backups(self, *, connection: Any, schema: str) -> tuple[StateBackupRecord, ...]:
        prefix: str = f"{schema}__backup_%"
        rows: list[tuple[Any, ...]] = connection.execute(
            "SELECT s.schema_name, e.backup_id, MAX(e.created_at) "
            "FROM information_schema.schemata s "
            "LEFT JOIN "
            f"{self._qualified_name(schema=schema, table=STATE_MIGRATION_EVENTS_TABLE)} e "
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

    def delete_state_backup(self, *, connection: Any, schema: str, backup_id: str) -> None:
        backup_schema: str = self._backup_schema_name(schema=schema, backup_id_value=backup_id)
        connection.execute(f"DROP SCHEMA IF EXISTS {self._quote_identifier(backup_schema)} CASCADE")

    def _latest_backup_id(self, *, connection: Any, schema: str) -> str:
        prefix: str = f"{schema}__backup_%"
        rows: list[tuple[str]] = connection.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE ? "
            "ORDER BY schema_name DESC LIMIT 1",
            [prefix],
        ).fetchall()
        if not rows:
            raise StateBackupNotFoundError("No state backup is available for rollback")
        return rows[0][0].removeprefix(f"{schema}__backup_")

    def _schema_exists(self, *, connection: Any, schema: str) -> bool:
        rows: list[tuple[str]] = connection.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = ?",
            [schema],
        ).fetchall()
        return bool(rows)

    def _record_event(
        self,
        *,
        connection: Any,
        schema: str,
        action: StateMigrationAction,
        backup_id_value: str | None,
        status: StateMigrationStatus,
        message: str | None,
    ) -> None:
        connection.execute(
            "INSERT INTO "
            f"{self._qualified_name(schema=schema, table=STATE_MIGRATION_EVENTS_TABLE)} "
            "(event_id, action, backup_id, status, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [event_id(), action.value, backup_id_value, status.value, message],
        )

    def _create_additional_state_tables(self, *, connection: Any, schema: str) -> None:
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
                "CREATE TABLE IF NOT EXISTS "
                f"{self._qualified_name(schema=schema, table=table_name)} "
                f"({column_sql})"
            )
            column_name: str
            column_type: StateColumnType
            for column_name, column_type in columns.items():
                connection.execute(
                    f"ALTER TABLE {self._qualified_name(schema=schema, table=table_name)} "
                    f"ADD COLUMN IF NOT EXISTS {self._quote_identifier(column_name)} "
                    f"{self._state_column_sql_type(column_type)}"
                )
        self._create_state_indexes(connection=connection, schema=schema)

    def _create_state_indexes(self, *, connection: Any, schema: str) -> None:
        table_name: str
        indexes: dict[str, tuple[str, ...]]
        for table_name, indexes in STATE_TABLE_INDEXES.items():
            index_name: str
            columns: tuple[str, ...]
            for index_name, columns in indexes.items():
                column_sql: str = ", ".join(self._quote_identifier(column) for column in columns)
                unique_sql: str = "" if index_name in NON_UNIQUE_STATE_INDEXES else "UNIQUE "
                connection.execute(
                    f"CREATE {unique_sql}INDEX IF NOT EXISTS {self._quote_identifier(index_name)} "
                    f"ON {self._qualified_name(schema=schema, table=table_name)} ({column_sql})"
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

    def _replace_virtual_environment_node_ref_groups(
        self,
        *,
        connection: Any,
        schema: str,
        virtual_environment_name: str,
        refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]],
    ) -> None:
        node_type: str
        refs: tuple[VirtualEnvironmentNodeRefRecord, ...]
        for node_type, refs in refs_by_node_type.items():
            temp_table_name: str = "__sqlbuild_replace_virtual_environment_node_refs"
            self._validate_node_ref_replacement(
                virtual_environment_name=virtual_environment_name,
                node_type=node_type,
                refs=refs,
            )
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            connection.execute(
                f"CREATE TEMP TABLE {temp_table_name} ("
                "virtual_environment_name TEXT NOT NULL, "
                "node_type TEXT NOT NULL, "
                "node_name TEXT NOT NULL, "
                "version_hash TEXT NOT NULL, "
                "UNIQUE (virtual_environment_name, node_type, node_name))"
            )
            ref: VirtualEnvironmentNodeRefRecord
            for ref in refs:
                connection.execute(
                    f"INSERT INTO {temp_table_name} "
                    "(virtual_environment_name, node_type, node_name, version_hash) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        ref.virtual_environment_name,
                        ref.node_type,
                        ref.node_name,
                        ref.version_hash,
                    ],
                )
            connection.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = ? AND node_type = ? "
                "AND NOT EXISTS ("
                f"SELECT 1 FROM {temp_table_name} incoming "
                "WHERE incoming.node_name = "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)}"
                ".node_name)",
                [virtual_environment_name, node_type],
            )
            connection.execute(
                "INSERT INTO "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "(virtual_environment_name, node_type, node_name, version_hash, updated_at) "
                "SELECT virtual_environment_name, node_type, node_name, version_hash, now() "
                f"FROM {temp_table_name} "
                "ON CONFLICT (virtual_environment_name, node_type, node_name) "
                "DO UPDATE SET version_hash = excluded.version_hash, updated_at = now()"
            )
            connection.execute(f"DROP TABLE IF EXISTS {temp_table_name}")

    def _backup_schema_name(self, *, schema: str, backup_id_value: str) -> str:
        return f"{schema}__backup_{backup_id_value}"

    def _state_type_matches(self, *, actual_type: str, expected_type: StateColumnType) -> bool:
        actual: str = actual_type.lower()
        match expected_type:
            case StateColumnType.INTEGER:
                return DUCKDB_INTEGER_TYPE_TOKEN in actual
            case StateColumnType.TEXT:
                return any(token in actual for token in ("text", "varchar", "character", "string"))
            case StateColumnType.TIMESTAMP:
                return DUCKDB_TIMESTAMP_TYPE_TOKEN in actual or DUCKDB_DATETIME_TYPE_TOKEN in actual
        return False
