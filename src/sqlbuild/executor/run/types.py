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
