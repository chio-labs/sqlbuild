"""Per-schema memory of Snowflake state-table retention fallbacks."""

from __future__ import annotations

import threading

from sqlbuild.adapters.snowflake._helpers.state_table_retention import (
    render_state_table_retention_sql,
)
from sqlbuild.adapters.snowflake.constants import (
    STATE_TABLE_FALLBACK_RETENTION_DAYS,
    STATE_TABLE_RETENTION_DAYS,
)


class StateTableRetentionFallbacks:
    """Track rendered state-table DDL and the schemas that rejected maximum retention."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._fallbacks: dict[str, tuple[tuple[str | None, str], str]] = {}
        self._fallback_schemas: set[tuple[str | None, str]] = set()

    def render(self, *, create_sql: str, database: str | None, schema: str) -> str:
        """Return the state-table DDL with the retention this schema currently accepts."""

        key: tuple[str | None, str] = (database, schema)
        preferred_sql: str = render_state_table_retention_sql(
            create_sql=create_sql, retention_days=STATE_TABLE_RETENTION_DAYS
        )
        fallback_sql: str = render_state_table_retention_sql(
            create_sql=create_sql, retention_days=STATE_TABLE_FALLBACK_RETENTION_DAYS
        )
        with self._lock:
            self._fallbacks[preferred_sql] = (key, fallback_sql)
            uses_fallback: bool = key in self._fallback_schemas
        return fallback_sql if uses_fallback else preferred_sql

    def fallback_for(self, sql: str) -> str | None:
        """Return the 1-day DDL for a rendered maximum-retention state-table statement."""

        with self._lock:
            entry: tuple[tuple[str | None, str], str] | None = self._fallbacks.get(sql)
        return None if entry is None else entry[1]

    def is_fallen_back(self, sql: str) -> bool:
        """Return whether the schema of a rendered state-table statement already fell back."""

        with self._lock:
            entry: tuple[tuple[str | None, str], str] | None = self._fallbacks.get(sql)
            return entry is not None and entry[0] in self._fallback_schemas

    def remember_fallback(self, sql: str) -> None:
        """Remember that the schema of a rendered state-table statement rejected 90 days."""

        with self._lock:
            entry: tuple[tuple[str | None, str], str] | None = self._fallbacks.get(sql)
            if entry is not None:
                self._fallback_schemas.add(entry[0])
