"""Executor run enum types."""

from __future__ import annotations

from enum import StrEnum


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
