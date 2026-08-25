"""Warehouse-backed direct-mode microbatch event store class."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.microbatches._helpers.sql import (
    build_insert_sql,
    build_read_scope_sql,
)
from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import (
    DIRECT_MICROBATCH_SCOPE_KIND,
    MICROBATCH_GENERATION_WILDCARD,
    MICROBATCH_WRITE_ATTEMPTS,
    MICROBATCH_WRITE_RETRY_BASE_SECONDS,
)
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope


class DirectMicrobatchEventStore:
    """Append/read microbatch history through a model worker's warehouse connection."""

    def __init__(self, *, adapter: BaseAdapter, connection: Any) -> None:
        self._adapter = adapter
        self._connection = connection

    def write(self, event: MicrobatchEvent) -> None:
        schema: str | None = event.scope.target_schema
        if schema is None:
            raise MicrobatchStateError("microbatch history requires a target schema")
        for attempt in range(MICROBATCH_WRITE_ATTEMPTS):
            try:
                self._adapter.execute(
                    connection=self._connection,
                    sql=self._adapter.render_create_microbatch_state_table_sql(
                        database=event.scope.target_database, schema=schema
                    ),
                )
                for index_sql in self._adapter.render_create_microbatch_state_index_sqls(
                    database=event.scope.target_database, schema=schema
                ):
                    self._adapter.execute(connection=self._connection, sql=index_sql)
                self._adapter.execute(
                    connection=self._connection,
                    sql=build_insert_sql(
                        event=event,
                        render_qualified_name=self._adapter.render_qualified_name,
                    ),
                )
                return
            except Exception:
                if attempt + 1 == MICROBATCH_WRITE_ATTEMPTS:
                    raise
                time.sleep(MICROBATCH_WRITE_RETRY_BASE_SECONDS * (attempt + 1))

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        schema: str | None = scope.target_schema
        if schema is None:
            raise MicrobatchStateError("microbatch history requires a target schema")
        self._adapter.execute(
            connection=self._connection,
            sql=self._adapter.render_create_microbatch_state_table_sql(
                database=scope.target_database, schema=schema
            ),
        )
        for index_sql in self._adapter.render_create_microbatch_state_index_sqls(
            database=scope.target_database, schema=schema
        ):
            self._adapter.execute(connection=self._connection, sql=index_sql)
        cursor: Any = self._adapter.execute(
            connection=self._connection,
            sql=build_read_scope_sql(
                scope=scope, render_qualified_name=self._adapter.render_qualified_name
            ),
        )
        return tuple(MicrobatchEventCodec.from_row(row) for row in cursor.fetchall())

    def read_model_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        return self.read_scope_history(
            replace(scope, physical_generation_id=MICROBATCH_GENERATION_WILDCARD)
        )


def direct_microbatch_scope(
    *, adapter: BaseAdapter, connection: Any, entry: ModelPlanEntry
) -> MicrobatchScope:
    """Build the direct logical scope for one destination relation."""

    qualified: str = (
        entry.destination.qualified_name
        or adapter.render_qualified_name(
            database=entry.destination.database,
            schema=entry.destination.schema,
            name=entry.destination.name,
        )
        or entry.destination.name
    )
    scope_key: str = f"{type(adapter).__module__}.{type(adapter).__name__}:{qualified}"
    generation: str = (
        adapter.physical_relation_generation(
            connection=connection,
            database=entry.destination.database,
            schema=entry.destination.schema,
            name=entry.destination.name,
        )
        or MICROBATCH_GENERATION_WILDCARD
    )
    return MicrobatchScope(
        scope_kind=DIRECT_MICROBATCH_SCOPE_KIND,
        scope_key=scope_key,
        model_name=entry.name,
        target_database=entry.destination.database,
        target_schema=entry.destination.schema,
        target_name=entry.destination.name,
        physical_generation_id=generation,
    )
