"""Diff execution exceptions."""

from __future__ import annotations

from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.diff.models import FullDiffModelSize


class FullDiffSizeGuardError(ExecutorInputError):
    """A default full comparison stopped before reading data because a table is too large."""

    code: str = "X320"

    def __init__(self, message: str, *, blocked: tuple[FullDiffModelSize, ...]) -> None:
        super().__init__(message)
        self.blocked = blocked
