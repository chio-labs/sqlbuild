"""Postgres state backend."""

from __future__ import annotations

from typing import Any

from sqlbuild.versioned.state.classes.duckdb import DuckDbStateBackend
from sqlbuild.versioned.state.constants import STATE_TABLE_COLUMNS
from sqlbuild.versioned.state.exceptions import StateBackendConfigError, StateBackupNotFoundError
from sqlbuild.versioned.state.helpers.validation import build_validation_result
from sqlbuild.versioned.state.models import StateSchemaValidationResult


class PostgresStateBackend(DuckDbStateBackend):
    """Postgres implementation for versioned state.

    The initial schema is intentionally aligned with DuckDB so lifecycle behavior can be
    tested through the shared state backend contract.
    """

    def connect(self, config: dict[str, object]) -> Any:
        try:
            import psycopg
        except ImportError as error:
            raise StateBackendConfigError(
                "Postgres state backend requires optional dependency psycopg. "
                "Install with: pip install 'psycopg[binary]' or sqlbuild[postgres]"
            ) from error

        return psycopg.connect(
            host=_optional_str(config.get("host")),
            port=_optional_int(config.get("port")),
            user=_optional_str(config.get("user")),
            password=_optional_str(config.get("password")),
            dbname=_optional_str(config.get("dbname")),
            autocommit=True,
        )

    def close(self, connection: Any) -> None:
        connection.close()

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


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
