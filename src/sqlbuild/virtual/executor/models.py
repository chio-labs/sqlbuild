"""Virtual executor result models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.shared.types import ExecutionResourceKind


@dataclass(frozen=True)
class VersionPrepareContext:
    """Context provided to optional custom prepare_version() functions in virtual mode."""

    adapter: BaseAdapter
    connection: Any
    prior_relation: str
    destination: str
    destination_database: str | None
    destination_schema: str | None
    destination_name: str
    config: dict[str, Any]
    placeholders: dict[str, str]
    run_id: str
    environment: str
    vars: dict[str, object]
    unique_key: tuple[str, ...]
    declared_columns: tuple[ColumnInfo, ...]
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
class VirtualBuildExecutionHooks:
    """Callbacks to use once a virtual build plan is ready."""

    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None
    on_node_complete: Callable[[object], None] | None = None
    on_sub_progress: Callable[[str], None] | None = None


@dataclass(frozen=True)
class VirtualBuildPipelineResult:
    """Result returned by the virtual build pipeline."""

    project: CompiledProject
    direct_plan_output: PlanOutput
    display_plan_output: PlanOutput
    execution_plan: PlanOutput
    execution_result: BuildExecutionResult
    python_node_results: tuple[PythonNodeExecutionResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class VirtualCloneItemResult:
    """One virtual clone hydration result."""

    model_name: str
    version_hash: str
    action: str
    message: str | None = None


@dataclass(frozen=True)
class VirtualCloneResult:
    """Result returned by virtual physical-version hydration."""

    mode: str
    source_environment: str
    target_environment: str
    target_virtual_environment: str | None = None
    item_results: tuple[VirtualCloneItemResult, ...] = field(default_factory=tuple)

    @property
    def selected_count(self) -> int:
        return len(self.item_results)

    @property
    def found_count(self) -> int:
        return sum(1 for item in self.item_results if item.action in {"hydrated", "reused"})

    @property
    def hydrated_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "hydrated")

    @property
    def reused_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "reused")

    @property
    def missing_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "missing")

    @property
    def skipped_locked_count(self) -> int:
        return sum(1 for item in self.item_results if item.action == "skipped_locked")
