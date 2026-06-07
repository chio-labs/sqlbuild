"""Source loader execution models."""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, LifeCycleEvent, StatementRecorder
from sqlbuild.adapter.shared.types import LoaderLogicalType
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer, _empty_provider_container
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class LoaderRowsSchema:
    """Tracked schema state for one or more loader row batches."""

    column_names: tuple[str, ...]
    inferred_types: dict[str, LoaderLogicalType]
    added_columns: tuple[ColumnInfo, ...]


@dataclass(frozen=True)
class LoaderRelationRef:
    """A loader-visible relation reference with cursor helpers."""

    name: str
    destination: str
    database: str | None
    schema: str | None
    table_name: str
    cursor_column: str | None
    adapter: BaseAdapter
    connection: Any
    statement_recorder: StatementRecorder

    @property
    def current_cursor_value(self) -> object | None:
        if self.cursor_column is None:
            return None
        return self.max(self.cursor_column)

    def max(self, column: str) -> object | None:
        if not self.adapter.relation_exists(
            self.connection,
            database=self.database,
            schema=self.schema,
            name=self.table_name,
        ):
            return None
        sql: str = f"SELECT MAX({column}) FROM {self.destination}"
        self.statement_recorder.record(sql)
        cursor: Any = self.adapter.execute(self.connection, sql)
        row: object | None = cursor.fetchone()
        if row is None:
            return None
        return row[0]


@dataclass(frozen=True)
class LoaderSkipResult:
    """User-facing skip signal returned by a source loader."""

    reason: str
    mode: SkipMode = SkipMode.SOFT


@dataclass(frozen=True)
class LoaderContext:
    """Runtime context passed to a source loader function."""

    adapter: BaseAdapter
    connection_config: dict[str, object]
    connection: Any
    destination: str
    destination_database: str | None
    destination_schema: str | None
    destination_name: str
    run_id: str
    target: str | None
    vars: dict[str, object]
    is_reload: bool
    use_color: bool
    current_cursor_value: object | None
    logger: logging.Logger
    statement_recorder: StatementRecorder
    start_cursor_ts: datetime | None = None
    end_cursor_ts: datetime | None = None
    start_cursor_int: int | None = None
    end_cursor_int: int | None = None
    loader_refs: Mapping[Callable[..., object], LoaderRelationRef] = field(default_factory=dict)
    source_refs: Mapping[str, LoaderRelationRef] = field(default_factory=dict)
    providers: ProviderContainer = field(default_factory=_empty_provider_container)

    def execute_sql(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def query(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def log(self, message: str) -> None:
        self.statement_recorder.log(message)

    def skip(self, reason: str, *, mode: SkipMode = SkipMode.SOFT) -> LoaderSkipResult:
        """Return a skip signal for the current source loader."""

        return LoaderSkipResult(reason=reason, mode=mode)

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
            database=self.destination_database if database is None else database,
            schema=self.destination_schema if schema is None else schema,
            name=name,
        )

    def qualify_in_destination_schema(self, name: str) -> str:
        """Return a relation name qualified into the destination database/schema."""

        return self.qualify_name(name)

    def loader(self, loader_fn: Callable[..., object]) -> LoaderRelationRef:
        """Return a relation reference for an upstream loader function."""

        relation_ref: LoaderRelationRef | None = self.loader_refs.get(loader_fn)
        if relation_ref is None:
            raise ExecutorInputError("Unknown loader reference passed to ctx.loader(...)")
        return relation_ref

    def source(self, source_name: str) -> LoaderRelationRef:
        """Return a relation reference for a project source by YAML source name."""

        relation_ref: LoaderRelationRef | None = self.source_refs.get(source_name)
        if relation_ref is None:
            raise ExecutorInputError(
                f"Unknown source reference passed to ctx.source(...): {source_name}"
            )
        return relation_ref


@dataclass(frozen=True)
class LoadExecutionResult:
    """Execution result for one source loader."""

    source_name: str
    loader_name: str
    status: ExecutionStatus
    target: str
    resource_kind: ExecutionResourceKind = ExecutionResourceKind.SOURCE
    staging_relation: str | None = None
    rows_loaded: int = 0
    duration_ms: int | None = None
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    skip_mode: SkipMode | None = None
    skip_reason: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class LoadExecutionIndexes:
    """Resolved loader/source indexes used during load execution."""

    loader_by_name: dict[str, DiscoveredLoaderFunction]
    source_by_name: dict[str, SourceEntry]
    source_by_loader_name: dict[str, SourceEntry]
    loader_ref_entries: dict[Callable[..., object], SourceEntry]
    loader_name_by_function: dict[Callable[..., object], str]
    has_loader_dependencies: bool


@dataclass
class LoadDagState:
    """Mutable scheduling state for concurrent source loader DAG execution."""

    results: list[LoadExecutionResult | None]
    in_degree: dict[str, int]
    ready: list[str]
    in_flight: set[str]
    failed_or_skipped: set[str]
    results_by_name: dict[str, LoadExecutionResult]
    source_index_by_name: dict[str, int]
    downstream_names: dict[str, tuple[str, ...]]
    completion_queue: queue.Queue[tuple[str, LoadExecutionResult]]
