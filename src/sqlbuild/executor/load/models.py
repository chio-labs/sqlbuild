"""Source loader execution models."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, LifeCycleEvent, StatementRecorder
from sqlbuild.adapter.shared.types import LoaderLogicalType
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts


@dataclass(frozen=True)
class LoaderRowsSchema:
    """Tracked schema state for one or more loader row batches."""

    column_names: tuple[str, ...]
    inferred_types: dict[str, LoaderLogicalType]
    added_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class LoaderContext:
    """Runtime context passed to a source loader function."""

    adapter: BaseAdapter
    connection: Any
    target: str
    target_database: str | None
    target_schema: str | None
    target_name: str
    run_id: str
    environment: str | None
    vars: dict[str, object]
    is_reload: bool
    current_cursor_value: object | None
    logger: logging.Logger
    statement_recorder: StatementRecorder

    def execute_sql(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def query(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def log(self, message: str) -> None:
        self.statement_recorder.log(message)

    def qualify_name(
        self,
        name: str,
        *,
        database: str | None = None,
        schema: str | None = None,
    ) -> str:
        """Return a fully-qualified relation name, preserving already-qualified input."""

        if "." in name:
            return name
        return resolve_qualified_name_parts(
            adapter=self.adapter,
            database=self.target_database if database is None else database,
            schema=self.target_schema if schema is None else schema,
            name=name,
        )

    def qualify_in_target_schema(self, name: str) -> str:
        """Return a relation name qualified into the target database/schema."""

        return self.qualify_name(name)


@dataclass(frozen=True)
class LoadExecutionResult:
    """Execution result for one source loader."""

    source_name: str
    loader_name: str
    status: ExecutionStatus
    target: str
    staging_relation: str | None = None
    rows_loaded: int = 0
    duration_ms: int | None = None
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    error_message: str | None = None
