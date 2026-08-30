"""Clone execution types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sqlbuild.executor.clone.models import CloneItemResult


class CloneItemCallback(Protocol):
    def __call__(self, *, index: int, total: int, item: CloneItemResult) -> None: ...


class CloneStartCallback(Protocol):
    def __call__(
        self, *, origin_target_name: str, destination_target_name: str, total: int
    ) -> None: ...


class CloneStatus(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"


class CloneAction(StrEnum):
    CLONED = "cloned"
    COPIED = "copied"
    RECREATED_VIEW = "recreated_view"
    RECREATED_FUNCTION = "recreated_function"
    WARNING_MISSING_SOURCE = "warning_missing_source"
    SKIPPED_MISSING_DEPENDENCY = "skipped_missing_dependency"
    FAILED = "failed"
