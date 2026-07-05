"""Shared CLI command models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter


@dataclass(frozen=True)
class AdapterConnectionContext:
    """Resolved adapter and connection configuration for one CLI command."""

    adapter_name: str
    adapter: BaseAdapter
    connection_config: dict[str, object]


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


from sqlbuild.cli.commands.shared.helpers.python_nodes.lifecycle_state import (  # noqa: E402,F401
    StandardPythonLifecycleState,
)
