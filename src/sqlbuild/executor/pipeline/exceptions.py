"""Execution pipeline errors."""

from __future__ import annotations

from sqlbuild.executor.pipeline.models import AuditExecutionFailure


class AuditExecutionError(RuntimeError):
    """Raised after every selected standalone audit has been attempted."""

    def __init__(self, *, failures: tuple[AuditExecutionFailure, ...]) -> None:
        self.failures: tuple[AuditExecutionFailure, ...] = failures
        lines: list[str] = [f"Standalone audit execution failed ({len(failures)} audits):"]
        lines.extend(
            f"  {failure.resource_id}: {failure.error_type}: {failure.message}"
            for failure in failures
        )
        super().__init__("\n".join(lines))


class AuditCoordinatorError(BaseException):
    """Marks callback failures that must stop standalone audit submission."""

    def __init__(self, error: BaseException) -> None:
        self.error: BaseException = error
        super().__init__(type(error).__name__)


class AuditConcurrencyError(RuntimeError):
    """Raised when standalone audit concurrency is invalid."""


class AuditOutcomeError(RuntimeError):
    """Raised when audit execution returns an unknown quality outcome."""
