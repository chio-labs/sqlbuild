"""Warehouse-backed direct-mode microbatch event store class."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.microbatches._helpers.sql import (
    build_existing_event_ids_sql,
    build_insert_many_sql,
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
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult

_EVENT_WRITE_CHUNK_SIZE: int = 250


class DirectMicrobatchEventStore:
    """Append/read microbatch history through a model worker's warehouse connection."""

    def __init__(self, *, adapter: BaseAdapter, connection: Any) -> None:
        self._adapter = adapter
        self._connection = connection
        self._initialized_tables: set[tuple[str | None, str]] = set()

    def write(self, event: MicrobatchEvent) -> None:
        self.write_many((event,))

    def write_many(self, events: tuple[MicrobatchEvent, ...]) -> MicrobatchWriteResult:
        if not events:
            return MicrobatchWriteResult(total=0, inserted=0, already_existing=0)
        first: MicrobatchEvent = events[0]
        schema: str | None = first.scope.target_schema
        if schema is None:
            raise MicrobatchStateError("microbatch history requires a target schema")
        self._initialize(database=first.scope.target_database, schema=schema)
        for attempt in range(MICROBATCH_WRITE_ATTEMPTS):
            try:
                inserted: int = 0
                for offset in range(0, len(events), _EVENT_WRITE_CHUNK_SIZE):
                    chunk: tuple[MicrobatchEvent, ...] = events[
                        offset : offset + _EVENT_WRITE_CHUNK_SIZE
                    ]
                    cursor: Any = self._adapter.execute(
                        connection=self._connection,
                        sql=build_existing_event_ids_sql(
                            events=chunk,
                            render_qualified_name=self._adapter.render_qualified_name,
                        ),
                    )
                    existing_ids: frozenset[str] = frozenset(
                        str(row[0]) for row in cursor.fetchall()
                    )
                    missing: tuple[MicrobatchEvent, ...] = tuple(
                        event for event in chunk if event.event_id not in existing_ids
                    )
                    if missing:
                        self._adapter.execute(
                            connection=self._connection,
                            sql=build_insert_many_sql(
                                events=missing,
                                render_qualified_name=self._adapter.render_qualified_name,
                            ),
                        )
                        inserted += len(missing)
                return MicrobatchWriteResult(
                    total=len(events),
                    inserted=inserted,
                    already_existing=len(events) - inserted,
                )
            except Exception:
                if attempt + 1 == MICROBATCH_WRITE_ATTEMPTS:
                    raise
                time.sleep(MICROBATCH_WRITE_RETRY_BASE_SECONDS * (attempt + 1))
        raise MicrobatchStateError("microbatch event publication exhausted retries")

    def _initialize(self, *, database: str | None, schema: str) -> None:
        identity: tuple[str | None, str] = (database, schema)
        if identity in self._initialized_tables:
            return
        self._adapter.execute(
            connection=self._connection,
            sql=self._adapter.render_create_microbatch_state_table_sql(
                database=database, schema=schema
            ),
        )
        for index_sql in self._adapter.render_create_microbatch_state_index_sqls(
            database=database, schema=schema
        ):
            self._adapter.execute(connection=self._connection, sql=index_sql)
        self._initialized_tables.add(identity)

    def read_scope_history(self, scope: MicrobatchScope) -> tuple[MicrobatchEvent, ...]:
        schema: str | None = scope.target_schema
        if schema is None:
            raise MicrobatchStateError("microbatch history requires a target schema")
        self._initialize(database=scope.target_database, schema=schema)
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

    return direct_microbatch_scope_for_location(
        adapter=adapter,
        connection=connection,
        model_name=entry.name,
        destination=entry.destination,
    )


def direct_microbatch_scope_for_location(
    *,
    adapter: BaseAdapter,
    connection: Any,
    model_name: str,
    destination: CompiledRelationLocation,
) -> MicrobatchScope:
    """Build a direct logical scope from non-executable model metadata."""

    qualified: str = (
        destination.qualified_name
        or adapter.render_qualified_name(
            database=destination.database,
            schema=destination.schema,
            name=destination.name,
        )
        or destination.name
    )
    scope_key: str = f"{type(adapter).__module__}.{type(adapter).__name__}:{qualified}"
    generation: str = (
        adapter.physical_relation_generation(
            connection=connection,
            database=destination.database,
            schema=destination.schema,
            name=destination.name,
        )
        or MICROBATCH_GENERATION_WILDCARD
    )
    return MicrobatchScope(
        scope_kind=DIRECT_MICROBATCH_SCOPE_KIND,
        scope_key=scope_key,
        model_name=model_name,
        target_database=destination.database,
        target_schema=destination.schema,
        target_name=destination.name,
        physical_generation_id=generation,
    )
