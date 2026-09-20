"""Terminal lifecycle event claims shared by CLI observability and output."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.runtime.observability.models import LifecycleEvent


@dataclass(frozen=True)
class TerminalEventClaim:
    """One claimed terminal with its immutable canonical publication sequence."""

    terminal: LifecycleEvent
    event_sequence: int
