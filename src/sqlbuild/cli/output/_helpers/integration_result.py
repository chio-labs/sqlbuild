"""Canonical integration-result projection from executor result models."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

from sqlbuild.cli.output._helpers.future_cursor_safety import serialize_future_cursor_safety
from sqlbuild.cli.output._helpers.integration_identity import integration_resource_id
from sqlbuild.cli.output._helpers.integration_validation import encode_integration_json
from sqlbuild.cli.output.constants import (
    INTEGRATION_RESOURCE_FAILED_EVENT,
    INTEGRATION_RESULT_RECORD_KIND,
    INTEGRATION_RESULT_SCHEMA_VERSION,
)
from sqlbuild.cli.output.models import (
    IntegrationAssetResult,
    IntegrationCheckResult,
    IntegrationResultEnvelope,
)
from sqlbuild.cli.output.types import IntegrationOutputKind
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import (
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.main.resource_id import sql_test_resource_id
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.runtime.observability.constants import RESOURCE_ATTEMPT_SKIPPED_EVENT
from sqlbuild.runtime.observability.exceptions import ObservabilityValidationError
from sqlbuild.runtime.observability.models import LifecycleEvent
from sqlbuild.runtime.observability.types import JSONValue


def build_integration_result(
    *,
    result: object,
    terminal: LifecycleEvent,
    event_sequence: int,
    plan: PlanOutput | None,
    command: str,
) -> IntegrationResultEnvelope | None:
    """Build one canonical terminal/result envelope for an integration callback."""

    asset: IntegrationAssetResult | None = _asset_result(result=result, plan=plan)
    if asset is not None:
        payload_kind: object = terminal.payload.get("resource_kind")
        payload_name: object = terminal.payload.get("resource_name")
        asset = replace(
            asset,
            kind=payload_kind if isinstance(payload_kind, str) else "",
            name=payload_name if isinstance(payload_name, str) else "",
            status=_canonical_status(terminal=terminal, fallback=asset.status),
        )
    checks: tuple[IntegrationCheckResult, ...] = _check_results(result=result)
    if asset is None and not checks:
        return None
    output_kind: IntegrationOutputKind = (
        IntegrationOutputKind.ASSET if asset is not None else IntegrationOutputKind.CHECK
    )
    payload: Mapping[str, JSONValue] = terminal.payload
    return IntegrationResultEnvelope(
        schema_version=INTEGRATION_RESULT_SCHEMA_VERSION,
        record_kind=INTEGRATION_RESULT_RECORD_KIND,
        event_id=terminal.event_id,
        event_sequence=event_sequence,
        event_type=terminal.event_type,
        occurred_at=terminal.occurred_at.isoformat(),
        invocation_id=terminal.invocation_id,
        run_id=terminal.run_id or "",
        resource_id=terminal.resource_id or "",
        resource_attempt_id=terminal.resource_attempt_id or "",
        operation_id=terminal.operation_id,
        statement_id=terminal.statement_id,
        resource_kind=str(payload.get("resource_kind") or ""),
        resource_name=str(payload.get("resource_name") or ""),
        attempt_number=_attempt_number(payload.get("attempt_number")),
        duration_ms=_number(payload.get("duration_ms")),
        output_kind=output_kind,
        command=command,
        error_code=_optional_text(payload.get("error_code")),
        error_type=_optional_text(payload.get("error_type")),
        skip_code=_optional_text(payload.get("skip_code")),
        skip_mode=_optional_text(payload.get("skip_mode")),
        asset=asset,
        checks=checks,
    )


def build_clone_integration_result(
    *, item: CloneItemResult, terminal: LifecycleEvent, event_sequence: int
) -> IntegrationResultEnvelope:
    """Build one canonical clone terminal/result envelope."""

    payload: Mapping[str, JSONValue] = terminal.payload
    return IntegrationResultEnvelope(
        schema_version=INTEGRATION_RESULT_SCHEMA_VERSION,
        record_kind=INTEGRATION_RESULT_RECORD_KIND,
        event_id=terminal.event_id,
        event_sequence=event_sequence,
        event_type=terminal.event_type,
        occurred_at=terminal.occurred_at.isoformat(),
        invocation_id=terminal.invocation_id,
        run_id=terminal.run_id or "",
        resource_id=terminal.resource_id or "",
        resource_attempt_id=terminal.resource_attempt_id or "",
        operation_id=terminal.operation_id,
        statement_id=terminal.statement_id,
        resource_kind=str(payload.get("resource_kind") or ""),
        resource_name=str(payload.get("resource_name") or ""),
        attempt_number=_attempt_number(payload.get("attempt_number")),
        duration_ms=_number(payload.get("duration_ms")),
        output_kind=IntegrationOutputKind.ASSET,
        command="clone",
        error_code=_optional_text(payload.get("error_code")),
        error_type=_optional_text(payload.get("error_type")),
        skip_code=_optional_text(payload.get("skip_code")),
        skip_mode=_optional_text(payload.get("skip_mode")),
        asset=IntegrationAssetResult(
            kind=str(payload.get("resource_kind") or ""),
            name=str(payload.get("resource_name") or ""),
            status=_canonical_status(terminal=terminal, fallback=item.status.value),
            action=item.action.value,
            target=item.destination_relation,
            origin_relation=item.origin_relation,
        ),
    )


def result_resource_identity(*, result: object) -> tuple[str | None, str | None]:
    """Return the canonical resource name and identifier for an executor result."""

    if isinstance(result, ModelExecutionResult):
        return result.model_name, integration_resource_id(
            resource_kind="model", resource_name=result.model_name, check_id=None
        )
    if isinstance(result, SeedExecutionResult):
        return result.seed_name, integration_resource_id(
            resource_kind="seed", resource_name=result.seed_name, check_id=None
        )
    if isinstance(result, FunctionExecutionResult):
        return result.function_name, integration_resource_id(
            resource_kind=result.function_kind,
            resource_name=result.function_name,
            check_id=None,
        )
    if isinstance(result, LoadExecutionResult):
        return result.source_name, integration_resource_id(
            resource_kind="source", resource_name=result.source_name, check_id=None
        )
    if isinstance(result, PythonNodeExecutionResult):
        return result.node_name, integration_resource_id(
            resource_kind=result.kind.value, resource_name=result.node_name, check_id=None
        )
    if isinstance(result, PythonCheckExecutionResult):
        check_id: str = f"check:{result.node_name}"
        return result.node_name, integration_resource_id(
            resource_kind="python_check", resource_name=result.node_name, check_id=check_id
        )
    if isinstance(result, SqlTestExecutionResult):
        check_id = _sql_test_check_id(result)
        return result.test_name, integration_resource_id(
            resource_kind="sql_test", resource_name=result.test_name, check_id=check_id
        )
    if isinstance(result, AuditExecutionResult):
        check_id = _audit_check_id(result)
        return result.audit_name, integration_resource_id(
            resource_kind="audit", resource_name=result.audit_name, check_id=check_id
        )
    return None, None


def _asset_result(*, result: object, plan: PlanOutput | None) -> IntegrationAssetResult | None:
    if isinstance(result, ModelExecutionResult):
        target: str | None = None
        if plan is not None and result.model_name in plan.model_locations:
            target = plan.model_locations[result.model_name].qualified_name
        return IntegrationAssetResult(
            kind=CompiledResourceType.MODEL.value,
            name=result.model_name,
            status=result.status.value,
            target=target or result.promoted_relation,
            staging_relation=result.staging_relation,
            failed_phase=result.failed_phase.value if result.failed_phase else None,
            future_cursor_safety=_bounded_metadata(
                serialize_future_cursor_safety(result.future_cursor_safety) or {}
            ),
            microbatch=_model_microbatch(result),
        )
    if isinstance(result, SeedExecutionResult):
        target = None
        if plan is not None and result.seed_name in plan.seed_locations:
            target = plan.seed_locations[result.seed_name].qualified_name
        return IntegrationAssetResult(
            kind=CompiledResourceType.SEED.value,
            name=result.seed_name,
            status=result.status.value,
            target=target,
        )
    if isinstance(result, FunctionExecutionResult):
        target = None
        if plan is not None and result.function_name in plan.function_locations:
            target = plan.function_locations[result.function_name].qualified_name
        return IntegrationAssetResult(
            kind=result.function_kind,
            name=result.function_name,
            status=result.status.value,
            target=target,
        )
    if isinstance(result, LoadExecutionResult):
        return IntegrationAssetResult(
            kind=result.resource_kind.value,
            name=result.source_name,
            status=result.status.value,
            target=result.target,
            staging_relation=result.staging_relation,
            loader=result.loader_name,
            rows_loaded=result.rows_loaded,
        )
    if isinstance(result, PythonNodeExecutionResult):
        return IntegrationAssetResult(
            kind=result.kind.value,
            name=result.node_name,
            status=result.status.value,
            materialized=result.materialized,
        )
    return None


def _check_results(*, result: object) -> tuple[IntegrationCheckResult, ...]:
    if isinstance(result, AuditExecutionResult):
        return (_audit_result(result),)
    if isinstance(result, SqlTestExecutionResult):
        asset_name: str | None = result.step_results[0].model_name if result.step_results else None
        return (
            IntegrationCheckResult(
                kind="sql_test",
                name=result.test_name,
                check_id=_sql_test_check_id(result),
                dag_check_id=_sql_test_check_id(result),
                passed=result.outcome == SqlTestOutcome.PASS,
                status=result.outcome.value,
                asset_name=asset_name,
            ),
        )
    if isinstance(result, PythonCheckExecutionResult):
        status: str = "pass" if result.passed else "warn" if result.warned else "fail"
        return (
            IntegrationCheckResult(
                kind="python_check",
                name=result.node_name,
                check_id=f"check:{result.node_name}",
                dag_check_id=f"check:{result.node_name}",
                passed=result.passed,
                status=status,
                severity=result.severity.value,
            ),
        )
    return ()


def _audit_result(result: AuditExecutionResult) -> IntegrationCheckResult:
    return IntegrationCheckResult(
        kind="audit",
        name=result.audit_name,
        check_id=_audit_check_id(result),
        dag_check_id=_audit_check_id(result),
        passed=result.outcome == AuditOutcome.PASS,
        status=result.outcome.value,
        severity=result.severity.value,
        row_count=result.row_count,
        attachment_kind=result.attachment_kind.value,
        asset_name=result.attached_target_name,
        attached_column_name=result.attached_column_name,
        attached_target_name=result.attached_target_name,
        run_scope_phase=result.run_scope_phase.value,
        reused=result.reused,
    )


def _audit_check_id(result: AuditExecutionResult) -> str:
    return audit_resource_id(
        audit_name=result.audit_name,
        attachment_kind=result.attachment_kind,
        attached_target_name=result.attached_target_name,
        attached_column_name=result.attached_column_name,
    )


def _sql_test_check_id(result: SqlTestExecutionResult) -> str:
    return sql_test_resource_id(
        test_name=result.test_name,
        source_path=result.source_path,
        block_index=result.block_index,
        case_name=result.case_name,
    )


def _bounded_metadata(value: Mapping[str, object]) -> Mapping[str, JSONValue]:
    try:
        encoded: str = encode_integration_json(value=value)
    except ObservabilityValidationError:
        return {}
    decoded: Any = json.loads(encoded)
    return cast(dict[str, JSONValue], decoded)


def _model_microbatch(result: ModelExecutionResult) -> Mapping[str, JSONValue]:
    if result.microbatch_run_type is None:
        return {}
    values: dict[str, object] = {
        "run_type": result.microbatch_run_type,
        "batch_count": result.batch_count,
        "batch_size": result.batch_size,
        "recovery_batch_count": result.microbatch_recovery_batch_count,
        "known_gap_count": result.microbatch_known_gap_count,
        "unaccounted_interval_count": result.microbatch_unaccounted_interval_count,
        "synthetic_completion_count": result.microbatch_synthetic_completion_count,
        "unknown_fingerprint_count": result.microbatch_unknown_fingerprint_count,
        "contiguous_frontier": result.microbatch_contiguous_frontier,
        "unaccounted_partition_policy": result.microbatch_unaccounted_partition_policy,
        "replay_requirement_id": result.microbatch_replay_requirement_id,
        "required_model_version_hash": result.microbatch_required_model_version_hash,
        "physical_generation_id": result.microbatch_physical_generation_id,
        "concurrent_enabled": result.microbatch_concurrent_enabled,
        "batch_concurrency": result.microbatch_batch_concurrency,
        "global_concurrency": result.microbatch_global_concurrency,
        "replay_requirement_state": result.microbatch_replay_requirement_state,
        "limit": result.microbatch_limit,
        "count": result.microbatch_limit_count,
        "action": (
            result.microbatch_limit_action.value
            if result.microbatch_limit_action is not None
            else None
        ),
    }
    return _bounded_metadata({key: value for key, value in values.items() if value is not None})


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _canonical_status(*, terminal: LifecycleEvent, fallback: str) -> str:
    if terminal.event_type == INTEGRATION_RESOURCE_FAILED_EVENT:
        return "failed"
    if terminal.event_type == RESOURCE_ATTEMPT_SKIPPED_EVENT:
        return "skipped"
    return fallback


def _attempt_number(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _number(value: object) -> int | float | None:
    return value if isinstance(value, int | float) else None
