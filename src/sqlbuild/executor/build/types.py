"""Build executor domain types."""

from __future__ import annotations

from enum import StrEnum

from sqlbuild.executor.shared.types import ExecutionStatus as ExecutionStatus
from sqlbuild.shared.types import ExecutionResourceKind as ExecutionResourceKind


class BuildStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
