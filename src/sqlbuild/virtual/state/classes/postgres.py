"""Postgres virtual-state backend."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Any, ClassVar

from sqlbuild.adapter.contract.classes.observed_connection import ObservedConnection
from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import (
    MICROBATCH_COLUMNS,
    MICROBATCH_GENERATION_WILDCARD,
    VIRTUAL_MICROBATCH_SCOPE_KIND,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult
from sqlbuild.virtual.state._helpers.state_storage.datetime import (
    to_naive_utc_wall_clock,
)
from sqlbuild.virtual.state._helpers.state_storage.events import backup_id, event_id
from sqlbuild.virtual.state._helpers.state_storage.validation import (
    build_validation_result,
)
from sqlbuild.virtual.state.classes._sql_state_backend import SqlStateBackend
from sqlbuild.virtual.state.constants import (
    CURRENT_STATE_SCHEMA_VERSION,
    LOCK_TABLE,
    MICROBATCH_EVENT_TABLE,
    NON_UNIQUE_STATE_INDEXES,
    POSTGRES_INTEGER_TYPES,
    POSTGRES_TEXT_TYPES,
    PYTHON_NODE_VERSION_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_MIGRATION_EVENTS_TABLE,
    STATE_TABLE_COLUMNS,
    STATE_TABLE_INDEXES,
    STATE_TABLES,
    STATE_VERSION_TABLE,
    VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
    VIRTUAL_ENVIRONMENT_TABLE,
)
from sqlbuild.virtual.state.exceptions import (
    StateBackendConfigError,
    StateBackupNotFoundError,
    StateSchemaInvalidError,
)
from sqlbuild.virtual.state.models import (
    SourceFreshnessRecord,
    StateBackupRecord,
    StateLockLease,
    StateSchemaValidationResult,
    VirtualEnvironmentNodeRefRecord,
)
from sqlbuild.virtual.state.types import (
    StateColumnType,
    StateMigrationAction,
    StateMigrationStatus,
)


class PostgresStateBackend(SqlStateBackend):
    """Postgres implementation for virtual state."""

    _placeholder: ClassVar[str] = "%s"

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

    def _fetch_one(
        self, *, connection: Any, sql: str, params: Sequence[object] | None = None
    ) -> tuple[Any, ...] | None:
        with connection.cursor() as cursor:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, params)
            return cursor.fetchone()

    def _fetch_all(
        self, *, connection: Any, sql: str, params: Sequence[object] | None = None
    ) -> list[tuple[Any, ...]]:
        with connection.cursor() as cursor:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, params)
            return cursor.fetchall()

    @contextmanager
    def _write_transaction(self, *, connection: Any) -> Iterator[Any]:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                yield cursor
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def _statement_executor(self, *, connection: Any) -> AbstractContextManager[Any]:
        return connection.cursor()

    def _execute_in(
        self, *, executor: Any, sql: str, params: Sequence[object] | None = None
    ) -> None:
        if params is None:
            executor.execute(sql)
            return
        executor.execute(sql, params)

    def _lease_is_owned(self, *, executor: Any, schema: str, lease: StateLockLease) -> bool:
        lock_table: str = self._qualified_name(schema=schema, table=LOCK_TABLE)
        executor.execute(
            f"SELECT lock_key FROM {lock_table} "
            "WHERE lock_key = %s AND owner_id = %s "
            "AND expires_at > CURRENT_TIMESTAMP FOR UPDATE",
            [lease.lock_key, lease.owner_id],
        )
        return executor.fetchone() is not None

    def _fetch_one_in(
        self, *, executor: Any, sql: str, params: Sequence[object]
    ) -> tuple[Any, ...] | None:
        executor.execute(sql, params)
        return executor.fetchone()

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
        return MicrobatchEventCodec.from_rows(tuple(row) for row in rows)

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
        return MicrobatchEventCodec.from_rows(tuple(row) for row in rows)

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
        return MicrobatchEventCodec.from_rows(tuple(row) for row in rows)

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
                            to_naive_utc_wall_clock(record.observed_at),
                        ],
                    )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
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

    def _state_column_sql_type(self, column_type: StateColumnType) -> str:
        match column_type:
            case StateColumnType.INTEGER:
                return "INTEGER"
            case StateColumnType.TEXT:
                return "TEXT"
            case StateColumnType.TIMESTAMP:
                return "TIMESTAMP"
        raise StateBackendConfigError(f"Unsupported state column type: {column_type}")

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
            self._validate_node_ref_replacement(
                virtual_environment_name=virtual_environment_name,
                node_type=node_type,
                refs=refs,
            )
            executor.execute(
                "DELETE FROM "
                f"{self._qualified_name(schema=schema, table=VIRTUAL_ENVIRONMENT_NODE_REF_TABLE)} "
                "WHERE virtual_environment_name = %s AND node_type = %s",
                [virtual_environment_name, node_type],
            )
            ref: VirtualEnvironmentNodeRefRecord
            for ref in refs:
                executor.execute(
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
