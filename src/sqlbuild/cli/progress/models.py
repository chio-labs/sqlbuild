"""CLI progress models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.auditing.types import AuditOutcome


@dataclass(frozen=True)
class CommandProgressReporters:
    """Connection and planning progress reporters bound to one output stream."""

    connection: ConnectionProgressReporter
    planning: PlanningProgressReporter


@dataclass(frozen=True)
class NestedProgressChildRow:
    """One child row rendered below a completed nested progress item."""

    label: str
    name: str
    status_text: str
    detail: str = ""


@dataclass(frozen=True)
class AuditDisplayEntry:
    """Aggregated audit result for display."""

    label: str
    display_name: str
    outcome: AuditOutcome
    total_row_count: int
    batch_pass: int
    batch_total: int
    reused: bool = False
    executed_sql: str | None = None


@dataclass(frozen=True)
class ExecutionCounts:
    """Aggregated pass, warning, failure, and skip counts."""

    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0

    @property
    def total_count(self) -> int:
        return self.pass_count + self.warn_count + self.fail_count + self.skip_count
