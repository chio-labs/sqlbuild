"""Executor domain types."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class WorkerSuccessBuilder[KeyT, ResultT, CompletionT](Protocol):
    def __call__(self, key: KeyT, /, *, result: ResultT) -> CompletionT: ...


class WorkerFailureBuilder[KeyT, CompletionT](Protocol):
    def __call__(self, key: KeyT, /, *, error: Exception) -> CompletionT: ...


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    CUSTOM_MATERIALIZATION = "custom_materialization"


class LifecycleNodeStatus(StrEnum):
    """Generic lifecycle scheduler node status."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
