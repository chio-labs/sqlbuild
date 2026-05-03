"""Types for user-defined custom materializations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo, StatementRecorder
from sqlbuild.compiler.planner.models import SchemaFinding
from sqlbuild.executor.auditing.models import AuditExecutionResult


@dataclass(frozen=True)
class MaterializationContext:
    """Context provided by the framework to a custom materialize() function."""

    adapter: BaseAdapter
    connection: Any
    target: str
    target_database: str | None
    target_schema: str | None
    target_name: str
    sql: str
    config: dict[str, Any]
    placeholders: dict[str, str]
    existing_relation: RelationInfo | None
    run_id: str
    environment: str
    vars: dict[str, str]
    unique_key: tuple[str, ...]
    declared_columns: tuple[ColumnInfo, ...]
    is_first_run: bool
    is_full_refresh: bool
    query_changed: bool
    schema_findings: tuple[SchemaFinding, ...]
    run_audits: Callable[[str], tuple[AuditExecutionResult, ...]]
    on_progress: Callable[[str], None] | None
    statement_recorder: StatementRecorder = field(default_factory=StatementRecorder)

    def execute_sql(self, sql: str) -> Any:
        """Execute a SQL statement, recording it for runtime artifacts and verbose output."""
        self.statement_recorder.record(sql)
        return self.adapter.execute(self.connection, sql)


@dataclass(frozen=True)
class MaterializationResult:
    """Result returned by a custom materialize() function."""

    relation: str
    failed: bool = False
    error: str | None = None
    cleanup_relations: tuple[str, ...] = field(default_factory=tuple)
    audit_results: tuple[AuditExecutionResult, ...] | None = None
