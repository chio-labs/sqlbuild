"""Types for user-defined custom materializations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo, StatementRecorder
from sqlbuild.compiler.planner.models import SchemaFinding
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts


@dataclass(frozen=True)
class MaterializationContext:
    """Context provided by the framework to a custom materialize() function."""

    adapter: BaseAdapter
    connection: Any
    destination: str
    destination_database: str | None
    destination_schema: str | None
    destination_name: str
    sql: str
    config: dict[str, Any]
    placeholders: dict[str, str]
    existing_relation: RelationInfo | None
    run_id: str
    build_target: str
    vars: dict[str, object]
    unique_key: tuple[str, ...]
    declared_columns: tuple[ColumnInfo, ...]
    is_first_run: bool
    is_full_refresh: bool
    query_changed: bool
    schema_findings: tuple[SchemaFinding, ...]
    run_audits: Callable[[str], tuple[AuditExecutionResult, ...]]
    on_progress: Callable[[str], None] | None
    logger: logging.Logger
    statement_recorder: StatementRecorder = field(default_factory=StatementRecorder)

    def execute_sql(self, sql: str) -> Any:
        """Execute a SQL statement, recording it for runtime artifacts and verbose output."""
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)

    def log(self, message: str) -> None:
        """Record a log message for verbose output."""
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
            database=self.destination_database if database is None else database,
            schema=self.destination_schema if schema is None else schema,
            name=name,
        )

    def qualify_in_destination_schema(self, name: str) -> str:
        """Return a relation name qualified into the destination database/schema."""

        return self.qualify_name(name)


@dataclass(frozen=True)
class MaterializationResult:
    """Result returned by a custom materialize() function."""

    relation: str
    failed: bool = False
    error: str | None = None
    cleanup_relations: tuple[str, ...] = field(default_factory=tuple)
    audit_results: tuple[AuditExecutionResult, ...] | None = None
