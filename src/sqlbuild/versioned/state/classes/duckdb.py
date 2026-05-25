"""DuckDB state backend."""

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


class DuckDbStateBackend(StateBackend):
    """DuckDB implementation for versioned state."""

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
