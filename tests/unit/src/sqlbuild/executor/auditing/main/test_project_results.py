"""Completed audit projection tests."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

import sqlbuild.executor.auditing._helpers.result_projection as projection_module
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.audit_results.exceptions import AuditResultStorageError
from sqlbuild.executor.audit_results.models import AuditResultRecord
from sqlbuild.executor.auditing.main._project_results import project_audit_result_batch
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.main.dispatcher_scope import dispatcher_scope
from sqlbuild.runtime.observability.main.identity_scope import identity_scope
from sqlbuild.runtime.observability.models import ExecutionIdentity, LifecycleEvent
from tests.unit.src.sqlbuild.executor.auditing.main._test_types import AuditExecutionCase
from tests.unit.src.sqlbuild.executor.auditing.main.helpers import (
    build_projection_entry,
    build_projection_result,
)


@pytest.mark.parametrize(
    "test_case",
    [AuditExecutionCase("executed projection", AuditOutcome.WARN)],
    ids=lambda case: case.description,
)
def test_given_executed_measurement_when_projected_then_builds_record_and_lifecycle_event(
    test_case: AuditExecutionCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[AuditResultRecord] = []

    def write_records(**kwargs: object) -> None:
        records.extend(cast(tuple[AuditResultRecord, ...], kwargs["records"]))

    monkeypatch.setattr(projection_module, "write_audit_result_records", write_records)
    dispatcher: EventDispatcher = EventDispatcher()
    events: list[LifecycleEvent] = []
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    plan: PlanOutput = PlanOutput(
        audit_entries=(build_projection_entry(),),
        model_locations={
            "orders": CompiledRelationLocation(
                database="warehouse", schema="analytics", name="orders", qualified_name=None
            )
        },
    )
    # Writer is replaced, so only method attributes passed into it are required.
    adapter: Any = cast(
        Any,
        SimpleNamespace(
            execute=lambda *args, **kwargs: None,
            render_qualified_name=lambda *args, **kwargs: None,
            render_framework_type=lambda *args, **kwargs: "",
            render_create_audit_result_table_sql=lambda *args, **kwargs: "",
            render_create_audit_result_index_sqls=lambda *args, **kwargs: (),
        ),
    )

    with (
        identity_scope(ExecutionIdentity(invocation_id="invocation", run_id="run")),
        dispatcher_scope(dispatcher),
    ):
        projection: Any = project_audit_result_batch(
            plan=plan,
            results=(build_projection_result(),),
            adapter=adapter,
            connection=object(),
        )

    assert projection.written_count == 1
    assert projection.degraded is False
    assert records[0].outcome == test_case.expected_outcome.value
    assert len(records) == 1
    assert records[0].violation_count is None
    assert records[0].measured_value == 95.0
    assert records[0].thresholds_json == (
        '{"error":{"limit":90.0,"operator":"below"},'
        '"warn":{"limit":100.0,"operator":"below"}}'
    )
    assert records[0].evidence_json == '[{"order_id":1}]'
    assert len(events) == 1
    assert events[0].event_type == "audit_completed"
    assert events[0].payload["result_id"] == records[0].result_id


@pytest.mark.parametrize(
    "test_case",
    [AuditExecutionCase("reused projection", AuditOutcome.WARN)],
    ids=lambda case: case.description,
)
def test_given_reused_measurement_when_projected_then_skips_history_and_event(
    test_case: AuditExecutionCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer_calls: list[object] = []
    monkeypatch.setattr(
        projection_module,
        "write_audit_result_records",
        lambda **kwargs: writer_calls.append(kwargs),
    )
    dispatcher: EventDispatcher = EventDispatcher()
    events: list[LifecycleEvent] = []
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    plan: PlanOutput = PlanOutput(audit_entries=(build_projection_entry(),))

    with (
        identity_scope(ExecutionIdentity(invocation_id="invocation", run_id="run")),
        dispatcher_scope(dispatcher),
    ):
        projection: Any = project_audit_result_batch(
            plan=plan,
            results=(replace(build_projection_result(), reused=True),),
            adapter=cast(Any, object()),
            connection=object(),
            storage_schema="analytics",
        )

    assert projection.attempted_count == 0
    assert build_projection_result().outcome == test_case.expected_outcome
    assert writer_calls == []
    assert events == []


@pytest.mark.parametrize(
    "test_case",
    [AuditExecutionCase("failed projection", AuditOutcome.WARN)],
    ids=lambda case: case.description,
)
def test_given_history_storage_failure_when_projected_then_reports_degradation_without_raising(
    test_case: AuditExecutionCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_write(**kwargs: object) -> None:
        del kwargs
        raise AuditResultStorageError("unavailable")

    monkeypatch.setattr(
        projection_module,
        "write_audit_result_records",
        fail_write,
    )
    adapter: Any = cast(
        Any,
        SimpleNamespace(
            execute=lambda *args, **kwargs: None,
            render_qualified_name=lambda *args, **kwargs: None,
            render_framework_type=lambda *args, **kwargs: "",
            render_create_audit_result_table_sql=lambda *args, **kwargs: "",
            render_create_audit_result_index_sqls=lambda *args, **kwargs: (),
        ),
    )
    plan: PlanOutput = PlanOutput(
        audit_entries=(build_projection_entry(),),
        model_locations={
            "orders": CompiledRelationLocation(
                database=None, schema="analytics", name="orders", qualified_name=None
            )
        },
    )

    with identity_scope(ExecutionIdentity(invocation_id="invocation", run_id="run")):
        projection: Any = project_audit_result_batch(
            plan=plan,
            results=(build_projection_result(),),
            adapter=adapter,
            connection=object(),
        )

    assert projection.degraded is True
    assert projection.attempted_count == 1
    assert projection.written_count == 0
    assert projection.failed_count == 1
    assert build_projection_result().outcome == test_case.expected_outcome


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
