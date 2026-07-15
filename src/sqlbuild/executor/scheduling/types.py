"""Executor scheduling types."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class WorkerSuccessBuilder[KeyT, ResultT, CompletionT](Protocol):
    def __call__(self, *, key: KeyT, result: ResultT) -> CompletionT: ...


class WorkerFailureBuilder[KeyT, CompletionT](Protocol):
    def __call__(self, *, key: KeyT, error: Exception) -> CompletionT: ...


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class LifecycleNodeStatus(StrEnum):
    """Generic lifecycle scheduler node status."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
