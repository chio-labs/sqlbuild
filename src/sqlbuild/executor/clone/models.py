"""Clone execution models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


@dataclass(frozen=True)
class CloneItemResult:
    name: str
    action: CloneAction
    status: CloneStatus
    message: str | None = None
    executed_statements: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CloneExecutionResult:
    item_results: tuple[CloneItemResult, ...] = field(default_factory=tuple)
