"""Build executor domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlbuild.compiler.planner.models import ModelPlanEntry

from sqlbuild.executor.shared.types import ExecutionStatus as ExecutionStatus
from sqlbuild.shared.types import ExecutionResourceKind as ExecutionResourceKind


class BeforeModelMaterializeCallback(Protocol):
    def __call__(self, *, entry: ModelPlanEntry, connection: Any) -> None: ...


class BuildStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
