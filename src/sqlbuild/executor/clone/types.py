"""Clone execution types."""

from __future__ import annotations

from enum import StrEnum


class CloneStatus(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"


class CloneAction(StrEnum):
    CLONED = "cloned"
    COPIED = "copied"
    RECREATED_VIEW = "recreated_view"
    WARNING_MISSING_SOURCE = "warning_missing_source"
    FAILED = "failed"
