"""Execution result construction helpers."""

from __future__ import annotations

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.constants import (
    RUN_AUDIT_FAILED_CODE,
    RUN_CONTRACT_FAILED_CODE,
    RUN_CUSTOM_MATERIALIZATION_FAILED_CODE,
    RUN_DML_FAILED_CODE,
    RUN_FINGERPRINT_FAILED_CODE,
    RUN_POST_HOOK_FAILED_CODE,
    RUN_PRE_HOOK_FAILED_CODE,
    RUN_PROMOTION_FAILED_CODE,
    RUN_SCHEMA_CHANGE_FAILED_CODE,
    RUN_STAGING_FAILED_CODE,
    RUN_TYPE_ENFORCEMENT_FAILED_CODE,
    RUN_UNKNOWN_FAILED_CODE,
)
from sqlbuild.executor.run.models import HookExecutionResult, ModelExecutionResult
from sqlbuild.executor.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.main.error_code import error_code
from sqlbuild.shared.main.error_help import error_help
from sqlbuild.shared.main.error_message import error_message


def build_failed_result(
    *,
    entry: ModelPlanEntry,
    phase: ExecutionPhase,
    error: str | BaseException,
    staging_relation: str | None = None,
    promoted_relation: str | None = None,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
    hook_results: list[HookExecutionResult] | None = None,
) -> ModelExecutionResult:
    """Build a failed ModelExecutionResult for a specific phase."""

    rendered_error, rendered_code, rendered_help = _render_failure_error(
        error=error, fallback_code=_fallback_code_for_phase(phase)
    )

    statement_recorder.log(f"model {entry.name} failed phase={phase.value} error={rendered_error}")
    if staging_relation is not None:
        statement_recorder.log(f"staging relation kept for inspection: {staging_relation}")

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.FAILED,
        failed_phase=phase,
        staging_relation=staging_relation,
        promoted_relation=promoted_relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results or ()),
        error_code=rendered_code,
        error_help=rendered_help,
        error_message=rendered_error,
    )


def build_skipped_result(
    *,
    entry: ModelPlanEntry,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
    hook_results: list[HookExecutionResult],
    staging_relation: str | None = None,
    promoted_relation: str | None = None,
) -> ModelExecutionResult:
    """Build a skipped ModelExecutionResult after a lifecycle skip signal."""

    skipped_hook: HookExecutionResult | None = _last_skipped_hook(hook_results)
    statement_recorder.log(f"model {entry.name} skipped by hook")
    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SKIPPED,
        staging_relation=staging_relation,
        promoted_relation=promoted_relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
        skip_mode=skipped_hook.skip_mode if skipped_hook is not None else None,
        skip_reason=skipped_hook.skip_reason if skipped_hook is not None else None,
    )


def _last_skipped_hook(
    hook_results: list[HookExecutionResult],
) -> HookExecutionResult | None:
    hook_result: HookExecutionResult
    for hook_result in reversed(hook_results):
        if hook_result.status == ExecutionStatus.SKIPPED:
            return hook_result
    return None


def _render_failure_error(
    *, error: str | BaseException, fallback_code: str
) -> tuple[str, str | None, str | None]:
    """Render legacy string failures and structured exceptions with a code."""

    if isinstance(error, str):
        return error, fallback_code, None
    return (
        error_message(error),
        error_code(error=error, fallback_code=fallback_code),
        error_help(error),
    )


def _fallback_code_for_phase(phase: ExecutionPhase) -> str:
    """Return the run diagnostic code for a failure phase."""

    if phase == ExecutionPhase.PRE_HOOK:
        return RUN_PRE_HOOK_FAILED_CODE
    if phase == ExecutionPhase.STAGING:
        return RUN_STAGING_FAILED_CODE
    if phase == ExecutionPhase.SCHEMA_CHANGE:
        return RUN_SCHEMA_CHANGE_FAILED_CODE
    if phase == ExecutionPhase.TYPE_ENFORCEMENT:
        return RUN_TYPE_ENFORCEMENT_FAILED_CODE
    if phase == ExecutionPhase.CONTRACT:
        return RUN_CONTRACT_FAILED_CODE
    if phase == ExecutionPhase.AUDIT:
        return RUN_AUDIT_FAILED_CODE
    if phase == ExecutionPhase.PROMOTION:
        return RUN_PROMOTION_FAILED_CODE
    if phase == ExecutionPhase.DML:
        return RUN_DML_FAILED_CODE
    if phase == ExecutionPhase.POST_HOOK:
        return RUN_POST_HOOK_FAILED_CODE
    if phase == ExecutionPhase.FINGERPRINT:
        return RUN_FINGERPRINT_FAILED_CODE
    if phase == ExecutionPhase.CUSTOM_MATERIALIZATION:
        return RUN_CUSTOM_MATERIALIZATION_FAILED_CODE
    return RUN_UNKNOWN_FAILED_CODE
