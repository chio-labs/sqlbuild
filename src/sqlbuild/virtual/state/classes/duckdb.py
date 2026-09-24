"""DuckDB virtual-state backend."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from datetime import datetime
from typing import Any, ClassVar

from sqlbuild.adapter.contract.classes.observed_connection import ObservedConnection
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from sqlbuild.virtual.state._helpers.state_storage.datetime import (
    to_naive_utc_wall_clock,
)
from sqlbuild.virtual.state._helpers.state_storage.microbatch_events import (
    append_duckdb_microbatch_event,
    append_duckdb_microbatch_events,
    read_duckdb_microbatch_model_history,
    read_duckdb_microbatch_retention_history,
    read_duckdb_microbatch_scope_history,
)
from sqlbuild.virtual.state._helpers.state_storage.validation import build_validation_result
from sqlbuild.virtual.state.classes._sql_state_backend import SqlStateBackend
from sqlbuild.virtual.state.constants import (
    DUCKDB_DATETIME_TYPE_TOKEN,
    DUCKDB_INTEGER_TYPE_TOKEN,
    DUCKDB_TIMESTAMP_TYPE_TOKEN,
    LOCK_TABLE,
    MICROBATCH_EVENT_TABLE,
    PYTHON_NODE_VERSION_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_TABLE_COLUMNS,
    STATE_TABLE_INDEXES,
    VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
    VIRTUAL_ENVIRONMENT_TABLE,
)
from sqlbuild.virtual.state.exceptions import (
    StateBackendConfigError,
)
from sqlbuild.virtual.state.models import (
    SourceFreshnessRecord,
    StateLockLease,
    StateSchemaValidationResult,
    VirtualEnvironmentNodeRefRecord,
)
from sqlbuild.virtual.state.types import (
    StateColumnType,
)


class DuckDbStateBackend(SqlStateBackend):
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

    def _statement_executor(self, *, connection: Any) -> AbstractContextManager[Any]:
        return nullcontext(connection)

    def _execute_in(
        self, *, executor: Any, sql: str, params: Sequence[object] | None = None
    ) -> None:
        if params is None:
            executor.execute(sql)
            return
        executor.execute(sql, params)

    def _lease_is_owned(self, *, executor: Any, schema: str, lease: StateLockLease) -> bool:
        owned: tuple[Any, ...] | None = executor.execute(
            f"UPDATE {self._qualified_name(schema=schema, table=LOCK_TABLE)} "
            "SET updated_at = CURRENT_TIMESTAMP "
            "WHERE lock_key = ? AND owner_id = ? AND expires_at > CURRENT_TIMESTAMP "
            "RETURNING lock_key",
            [lease.lock_key, lease.owner_id],
        ).fetchone()
        return owned is not None

    def _fetch_one_in(
        self, *, executor: Any, sql: str, params: Sequence[object]
    ) -> tuple[Any, ...] | None:
        return executor.execute(sql, params).fetchone()

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

    def delete_state_backup(self, *, connection: Any, schema: str, backup_id: str) -> None:
        backup_schema: str = self._backup_schema_name(schema=schema, backup_id_value=backup_id)
        connection.execute(f"DROP SCHEMA IF EXISTS {self._quote_identifier(backup_schema)} CASCADE")

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

    def _replace_virtual_environment_node_ref_groups(
        self,
        *,
        executor: Any,
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
            executor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")
            executor.execute(
                f"CREATE TEMP TABLE {temp_table_name} ("
                "virtual_environment_name TEXT NOT NULL, "
                "node_type TEXT NOT NULL, "
                "node_name TEXT NOT NULL, "
                "version_hash TEXT NOT NULL, "
                "UNIQUE (virtual_environment_name, node_type, node_name))"
            )
            ref: VirtualEnvironmentNodeRefRecord
            for ref in refs:
                executor.execute(
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
            executor.execute(
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
            executor.execute(
                "INSERT INTO "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "(virtual_environment_name, node_type, node_name, version_hash, updated_at) "
                "SELECT virtual_environment_name, node_type, node_name, version_hash, now() "
                f"FROM {temp_table_name} "
                "ON CONFLICT (virtual_environment_name, node_type, node_name) "
                "DO UPDATE SET version_hash = excluded.version_hash, updated_at = now()"
            )
            executor.execute(f"DROP TABLE IF EXISTS {temp_table_name}")

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
