"""CLI progress models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter


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
