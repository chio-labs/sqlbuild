"""Python read-side SQL result helpers."""

from __future__ import annotations

from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus


def _sql_result_name(result: object) -> str | None:
    if isinstance(result, ModelExecutionResult):
        return result.model_name
    if isinstance(result, LoadExecutionResult):
        return result.source_name
    return None


def _sql_result_failed(result: object) -> bool:
    if isinstance(result, ModelExecutionResult | LoadExecutionResult):
        return result.status == ExecutionStatus.FAILED
    return False
