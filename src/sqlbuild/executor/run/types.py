"""Executor run enum types."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlbuild.executor.run.models import BatchWindow, MicrobatchPhaseOutcome


class MicrobatchBatchExecutor(Protocol):
    """Execute one microbatch window on one supplied connection."""

    def __call__(self, batch: BatchWindow, connection: Any, /) -> MicrobatchPhaseOutcome: ...


class MicrobatchBatchRunner(Protocol):
    """Run microbatch windows within the shared global worker budget."""

    def __call__(
        self,
        batches: tuple[BatchWindow, ...],
        concurrency: int,
        execute: MicrobatchBatchExecutor,
        /,
    ) -> tuple[MicrobatchPhaseOutcome, ...]: ...


class ExecutionPhase(StrEnum):
    PRE_HOOK = "pre_hook"
    STAGING = "staging"
    SCHEMA_CHANGE = "schema_change"
    TYPE_ENFORCEMENT = "type_enforcement"
    CONTRACT = "contract"
    AUDIT = "audit"
    PROMOTION = "promotion"
    DML = "dml"
    POST_HOOK = "post_hook"
    FINGERPRINT = "fingerprint"
    MICROBATCH_STATE = "microbatch_state"
    CUSTOM_MATERIALIZATION = "custom_materialization"


class HookPhase(StrEnum):
    PRE_HOOKS = "pre_hooks"
    POST_HOOKS = "post_hooks"


class AuditGateMode(StrEnum):
    EXECUTED = "executed"


class AuditGateStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class AuditGateReuseReason(StrEnum):
    REUSABLE = "reusable"
    MISSING = "missing"
    MALFORMED = "malformed"
    NON_PASSING = "non_passing"
    BINDING_SET_CHANGED = "binding_set_changed"
    AUDIT_CHANGED = "audit_changed"
    ALWAYS_RUN = "always_run"
