"""Warehouse-backed direct archive event store."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.archives._helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
    build_read_schema_sql,
    build_read_target_sql,
)
from sqlbuild.archives.classes.event_codec import ArchiveEventCodec
from sqlbuild.archives.constants import (
    ARCHIVE_WRITE_ATTEMPTS,
    ARCHIVE_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.archives.models import ArchiveEvent


class DirectArchiveEventStore:
    """Append/read archive facts through one worker warehouse connection."""

    def __init__(self, *, adapter: BaseAdapter, connection: Any) -> None:
        self._adapter = adapter
        self._connection = connection

    def write(self, event: ArchiveEvent) -> None:
        for attempt in range(ARCHIVE_WRITE_ATTEMPTS):
            try:
                self._ensure_table(database=event.target_database, schema=event.target_schema)
                self._adapter.execute(
                    connection=self._connection,
                    sql=build_insert_sql(
                        event=event,
                        render_qualified_name=self._adapter.render_qualified_name,
                    ),
                )
                return
            except Exception:
                if attempt + 1 == ARCHIVE_WRITE_ATTEMPTS:
                    raise
                time.sleep(ARCHIVE_WRITE_RETRY_BASE_SECONDS * (attempt + 1))

    def read_target_history(
        self, *, database: str | None, schema: str, target_name: str
    ) -> tuple[ArchiveEvent, ...]:
        self._ensure_table(database=database, schema=schema)
        cursor: Any = self._adapter.execute(
            connection=self._connection,
            sql=build_read_target_sql(
                database=database,
                schema=schema,
                target_name=target_name,
                render_qualified_name=self._adapter.render_qualified_name,
            ),
        )
        return tuple(ArchiveEventCodec.from_row(row) for row in cursor.fetchall())

    def read_schema_history(self, *, database: str | None, schema: str) -> tuple[ArchiveEvent, ...]:
        cursor: Any = self._adapter.execute(
            connection=self._connection,
            sql=build_read_schema_sql(
                database=database,
                schema=schema,
                render_qualified_name=self._adapter.render_qualified_name,
            ),
        )
        return tuple(ArchiveEventCodec.from_row(row) for row in cursor.fetchall())

    def _ensure_table(self, *, database: str | None, schema: str) -> None:
        self._adapter.execute(
            connection=self._connection,
            sql=build_create_table_sql(
                database=database,
                schema=schema,
                render_qualified_name=self._adapter.render_qualified_name,
                render_framework_type=self._adapter.render_framework_type,
            ),
        )
