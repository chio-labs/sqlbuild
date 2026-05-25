"""Postgres state backend."""

from __future__ import annotations

from typing import Any

from sqlbuild.versioned.state.classes.state_backend import StateBackend
from sqlbuild.versioned.state.constants import (
    CURRENT_STATE_SCHEMA_VERSION,
    STATE_MIGRATION_EVENTS_TABLE,
    STATE_TABLE_COLUMNS,
    STATE_TABLES,
    STATE_VERSION_TABLE,
)
from sqlbuild.versioned.state.exceptions import (
    StateBackendConfigError,
    StateBackupNotFoundError,
    StateSchemaInvalidError,
)
from sqlbuild.versioned.state.helpers.events import backup_id, event_id
from sqlbuild.versioned.state.helpers.validation import build_validation_result
from sqlbuild.versioned.state.models import StateSchemaValidationResult
from sqlbuild.versioned.state.types import (
    StateColumnType,
    StateMigrationAction,
    StateMigrationStatus,
)


class PostgresStateBackend(StateBackend):
    """Postgres implementation for versioned state."""

    def connect(self, config: dict[str, object]) -> Any:
        try:
            import psycopg
        except ImportError as error:
            raise StateBackendConfigError(
                "Postgres state backend requires optional dependency psycopg. "
                "Install with: pip install 'psycopg[binary]' or sqlbuild[postgres]"
            ) from error

        try:
            return psycopg.connect(
                host=_optional_str(config.get("host")),
                port=_optional_int(config.get("port")),
                user=_optional_str(config.get("user")),
                password=_optional_str(config.get("password")),
                dbname=_optional_str(config.get("dbname")),
                autocommit=True,
            )
        except Exception as error:
            raise StateBackendConfigError("Could not connect to Postgres state backend") from error

    def close(self, connection: Any) -> None:
        connection.close()

    def initialize(self, connection: Any, *, schema: str, sqlbuild_version: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
                cursor.execute(
                    "CREATE TABLE IF NOT EXISTS "
                    f"{self._qualified_name(schema, STATE_VERSION_TABLE)} ("
                    "schema_version INTEGER NOT NULL, "
                    "sqlbuild_version TEXT NOT NULL, "
                    "updated_at TIMESTAMP NOT NULL"
                    ")"
                )
                cursor.execute(
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
                cursor.execute(f"DELETE FROM {self._qualified_name(schema, STATE_VERSION_TABLE)}")
                cursor.execute(
                    f"INSERT INTO {self._qualified_name(schema, STATE_VERSION_TABLE)} "
                    "(schema_version, sqlbuild_version, updated_at) "
                    "VALUES (%s, %s, CURRENT_TIMESTAMP)",
                    [CURRENT_STATE_SCHEMA_VERSION, sqlbuild_version],
                )
                self._record_event(
                    cursor,
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

    def validate_schema(self, connection: Any, *, schema: str) -> StateSchemaValidationResult:
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
        return build_validation_result(
            existing_tables=tables,
            columns_by_table=columns_by_table,
            expected_columns=STATE_TABLE_COLUMNS,
            type_matches=self._state_type_matches,
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
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                cursor.execute(f"CREATE SCHEMA {self._quote_identifier(backup_schema)}")
                table_name: str
                for table_name in STATE_TABLES:
                    cursor.execute(
                        f"CREATE TABLE {self._qualified_name(backup_schema, table_name)} AS "
                        f"SELECT * FROM {self._qualified_name(schema, table_name)}"
                    )
                self._record_event(
                    cursor,
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

    def rollback(self, connection: Any, *, schema: str, backup_id: str | None = None) -> str:
        backup_id_value: str = backup_id or self._latest_backup_id(connection, schema=schema)
        backup_schema: str = self._backup_schema_name(
            schema=schema,
            backup_id_value=backup_id_value,
        )
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                table_name: str
                for table_name in STATE_TABLES:
                    cursor.execute(
                        f"DROP TABLE IF EXISTS {self._qualified_name(schema, table_name)}"
                    )
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {self._quote_identifier(schema)}")
                for table_name in STATE_TABLES:
                    cursor.execute(
                        f"CREATE TABLE {self._qualified_name(schema, table_name)} AS "
                        f"SELECT * FROM {self._qualified_name(backup_schema, table_name)}"
                    )
                self._record_event(
                    cursor,
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

    def reset(self, connection: Any, *, schema: str) -> None:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            try:
                table_name: str
                for table_name in STATE_TABLES:
                    cursor.execute(
                        f"DROP TABLE IF EXISTS {self._qualified_name(schema, table_name)}"
                    )
                cursor.execute("COMMIT")
            except BaseException:
                cursor.execute("ROLLBACK")
                raise

    def _latest_backup_id(self, connection: Any, *, schema: str) -> str:
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

    def _record_event(
        self,
        cursor: Any,
        *,
        schema: str,
        action: StateMigrationAction,
        backup_id_value: str | None,
        status: StateMigrationStatus,
        message: str | None,
    ) -> None:
        cursor.execute(
            f"INSERT INTO {self._qualified_name(schema, STATE_MIGRATION_EVENTS_TABLE)} "
            "(event_id, action, backup_id, status, message, created_at) "
            "VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            [event_id(), action.value, backup_id_value, status.value, message],
        )

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
                return actual in {"integer", "bigint", "smallint"}
            case StateColumnType.TEXT:
                return actual in {"text", "character varying", "character"}
            case StateColumnType.TIMESTAMP:
                return actual.startswith("timestamp")
        return False


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
