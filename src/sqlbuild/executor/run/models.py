"""Executor run domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus


@dataclass(frozen=True)
class ModelExecutionResult:
    """Outcome of one model materialization lifecycle."""

    model_name: str
    status: ExecutionStatus
    failed_phase: ExecutionPhase | None = None
    staging_relation: str | None = None
    promoted_relation: str | None = None
    audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    warning_messages: tuple[str, ...] = field(default_factory=tuple)
    error_message: str | None = None
