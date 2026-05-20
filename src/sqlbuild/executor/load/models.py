"""Source loader execution models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import LifeCycleEvent, StatementRecorder
from sqlbuild.executor.shared.types import ExecutionStatus


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
    statement_recorder: StatementRecorder

    def execute_sql(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def query(self, sql: str) -> Any:
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def log(self, message: str) -> None:
        self.statement_recorder.log(message)


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
