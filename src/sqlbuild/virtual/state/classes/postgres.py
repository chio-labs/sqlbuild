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
from sqlbuild.virtual.state._helpers.state_storage.validation import (
    build_validation_result,
)
from sqlbuild.virtual.state.classes._sql_state_backend import SqlStateBackend
from sqlbuild.virtual.state.constants import (
    LOCK_TABLE,
    MICROBATCH_EVENT_TABLE,
    POSTGRES_INTEGER_TYPES,
    POSTGRES_TEXT_TYPES,
    PYTHON_NODE_VERSION_TABLE,
    SOURCE_FRESHNESS_OBSERVATION_TABLE,
    STATE_TABLE_COLUMNS,
    STATE_TABLE_INDEXES,
    VIRTUAL_ENVIRONMENT_NODE_REF_TABLE,
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
                row_placeholders: str = (
                    "("
                    + ", ".join(
                        f"%s::{
                            self._state_column_sql_type(
                                STATE_TABLE_COLUMNS[MICROBATCH_EVENT_TABLE][column]
                            )
                        }"
                        for column in MICROBATCH_COLUMNS
                    )
                    + ")"
                )
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

    def delete_state_backup(self, *, connection: Any, schema: str, backup_id: str) -> None:
        backup_schema: str = self._backup_schema_name(schema=schema, backup_id_value=backup_id)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {self._quote_identifier(backup_schema)} CASCADE")
        connection.commit()

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
