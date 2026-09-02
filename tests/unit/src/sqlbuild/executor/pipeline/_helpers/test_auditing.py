"""Tests for standalone audit pipeline lifecycle ordering."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline._helpers.auditing import run_audit_pipeline
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    AuditPipelineLifecycleTestCase,
    AuditResourceIdentityTestCase,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers.helpers import (
    lifecycle_events_with_prefix,
    lifecycle_order_with_prefix,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AuditPipelineLifecycleTestCase(
            description="warning audit completes canonical attempt around callbacks",
            expected_event_type="resource_attempt_completed",
            expected_order=(
                "resource_attempt_started",
                "callback_start",
                "operation_started",
                "statement_started",
                "statement_completed",
                "operation_completed",
                "resource_attempt_completed",
                "callback_complete",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_warning_audit_when_run_then_start_and_completed_terminal_wrap_callbacks(
    tmp_path: Path,
    test_case: AuditPipelineLifecycleTestCase,
) -> None:
    entry: AuditPlanEntry = AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name="warn_audit"),
        name="warn_audit",
        resolved_sql="SELECT 1",
        unresolved_sql="SELECT 1",
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.WARN,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        attached_target_name="orders",
        attached_column_name="order_id",
    )
    result: AuditExecutionResult = AuditExecutionResult(
        audit_name="warn_audit",
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.WARN,
        outcome=AuditOutcome.WARN,
        row_count=1,
        executed_sql="SELECT 1",
        attached_target_name="orders",
        attached_column_name="order_id",
    )
    order: list[str] = []
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()

    def record_event(event: LifecycleEvent) -> None:
        events.append(event)
        order.append(event.event_type)

    dispatcher.subscribe_lifecycle(subscriber=record_event, accepts_opaque=False)
    with invocation_scope("audit-invocation"), dispatcher_scope(dispatcher):
        results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
            plan=PlanOutput(audit_entries=(entry,)),
            connection_config={"database": str(tmp_path / "audit.duckdb")},
            adapter=DuckDbAdapter(),
            on_audit_start=lambda _entry: order.append("callback_start"),
            on_audit_complete=lambda _result: order.append("callback_complete"),
            run_id="audit-run",
        )

    assert results[0].outcome == result.outcome
    lifecycle_order: tuple[str, ...] = lifecycle_order_with_prefix(
        order=order,
        prefixes=("resource_attempt_", "operation_", "statement_", "callback_"),
    )
    assert lifecycle_order == test_case.expected_order
    assert events[-1].event_type == test_case.expected_event_type
    assert all(event.run_id == "audit-run" for event in events)
    resource_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefixes=("resource_",)
    )
    assert tuple(event.resource_id for event in resource_events) == (
        "audit:warn_audit:model:orders:order_id",
        "audit:warn_audit:model:orders:order_id",
    )
    assert tuple(event.payload["resource_name"] for event in resource_events) == (
        "warn_audit",
        "warn_audit",
    )
    operation_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefixes=("operation_",)
    )
    statement_events: tuple[LifecycleEvent, ...] = lifecycle_events_with_prefix(
        events=events, prefixes=("statement_",)
    )
    assert len(operation_events) == 2
    assert all(
        event.resource_attempt_id == operation_events[0].resource_attempt_id
        for event in statement_events
    )
    assert all(event.operation_id == operation_events[0].operation_id for event in statement_events)
    assert "SELECT 1" not in str(operation_events)
    assert results[0].attached_column_name == "order_id"


@pytest.mark.parametrize(
    "test_case",
    (
        AuditResourceIdentityTestCase(
            description="same generic column audit on two targets has distinct identities",
            expected_first_id="audit:not_null:model:orders:id",
            expected_second_id="audit:not_null:model:customers:id",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_same_audit_and_column_on_two_targets_when_formatted_then_ids_remain_distinct(
    test_case: AuditResourceIdentityTestCase,
) -> None:
    first_id: str = audit_resource_id(
        audit_name="not_null",
        attachment_kind=AuditAttachmentKind.MODEL,
        attached_target_name="orders",
        attached_column_name="id",
    )
    second_id: str = audit_resource_id(
        audit_name="not_null",
        attachment_kind=AuditAttachmentKind.MODEL,
        attached_target_name="customers",
        attached_column_name="id",
    )

    assert first_id == test_case.expected_first_id
    assert second_id == test_case.expected_second_id
    assert first_id != second_id
