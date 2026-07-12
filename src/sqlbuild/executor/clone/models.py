"""Clone execution models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.models import LifeCycleEvent
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


@dataclass(frozen=True)
class CloneItemResult:
    name: str
    action: CloneAction
    status: CloneStatus
    message: str | None = None
    origin_relation: str | None = None
    destination_relation: str | None = None
    duration_seconds: float | None = None
    executed_statements: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PrephaseProgressRow:
    """One clone prephase progress row."""

    label: str
    name: str
    status: str
    duration_seconds: float | None = None
    caused_by_names: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class CloneExecutionResult:
    item_results: tuple[CloneItemResult, ...] = field(default_factory=tuple)
