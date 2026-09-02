"""Tests for canonical compatibility output projection."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Event, Thread

import pytest

from sqlbuild.cli.output.classes.compatibility_event_projector import (
    CompatibilityEventProjector,
    compatibility_event_projector_scope,
    current_compatibility_event_projector,
)
from sqlbuild.cli.output.classes.execution_event_writer import ExecutionEventWriter
from sqlbuild.cli.output.main._build_execution_json import format_build_execution_json
from sqlbuild.cli.output.main._build_item_execution_event import (
    format_build_item_execution_event,
)
from sqlbuild.cli.output.main._run_execution_json import format_run_execution_json
from sqlbuild.cli.output.main._scenario_execution_json import format_scenario_execution_json
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.constants import BUILD_SOURCE_FRESHNESS_BLOCKED_CODE
from sqlbuild.executor.build.main.aggregate_result import aggregate_build_result
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario.models import ScenarioRunResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.python_nodes.types import PythonCheckSeverity
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.unit.src.sqlbuild.cli.commands.shared._helpers.helpers import build_audit_result
from tests.unit.src.sqlbuild.cli.output.classes._test_types import (
    CompatibilityProjectionTestCase,
    PythonCheckProjectionTestCase,
)
from tests.unit.src.sqlbuild.cli.output.main.plan.helpers import (
    build_model_entry,
    build_plan_output,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("duplicate terminal is claimed once", 42),),
    ids=lambda case: case.description,
)
def test_given_duplicate_terminal_when_projecting_then_event_is_stored_and_claimed_once(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    terminal: LifecycleEvent = lifecycle_event(
        "resource_attempt_completed",
        run_id="run-1",
        resource_id="model:orders",
        resource_attempt_id="attempt-1",
        payload={
            "resource_kind": "model",
            "resource_name": "orders",
            "attempt_number": 1,
            "duration_ms": 42.4,
        },
    )
    projector.consume(terminal)
    projector.consume(terminal)

    with compatibility_event_projector_scope(projector):
        first: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.SUCCESS,
                duration_ms=999,
            ),
            plan=None,
        )
        second: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.SUCCESS,
                duration_ms=999,
            ),
            plan=None,
        )

    assert len(projector.events()) == 1
    assert first is not None
    assert json.loads(first)["asset"]["duration_ms"] == test_case.expected_output
    assert second is None


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("missing terminal emits nothing", None),),
    ids=lambda case: case.description,
)
def test_given_missing_terminal_when_projecting_then_no_v1_terminal_is_fabricated(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()

    with compatibility_event_projector_scope(projector):
        result: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.SUCCESS,
            ),
            plan=None,
        )

    assert result is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("nested scope restores outer projector", None),),
    ids=lambda case: case.description,
)
def test_given_nested_projection_scope_when_restored_then_previous_context_is_preserved(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    outer: CompatibilityEventProjector = CompatibilityEventProjector()
    inner: CompatibilityEventProjector = CompatibilityEventProjector()
    unrelated: LifecycleEvent = replace(lifecycle_event(), event_id="outer-event")
    outer.consume(unrelated)

    with compatibility_event_projector_scope(outer):
        with compatibility_event_projector_scope(inner):
            assert current_compatibility_event_projector() is inner
        assert current_compatibility_event_projector() is outer

    assert current_compatibility_event_projector() is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (
        CompatibilityProjectionTestCase(
            "callback race follows canonical terminal order", ("a", "b")
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_reverse_callbacks_when_projecting_then_canonical_order_is_preserved(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    first: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_completed",
            run_id="run-1",
            resource_id="model:a",
            resource_attempt_id="attempt-a",
            payload={
                "resource_kind": "model",
                "resource_name": "a",
                "attempt_number": 1,
                "duration_ms": 1,
            },
        ),
        event_id="event-a",
    )
    second: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_completed",
            run_id="run-1",
            resource_id="model:b",
            resource_attempt_id="attempt-b",
            payload={
                "resource_kind": "model",
                "resource_name": "b",
                "attempt_number": 1,
                "duration_ms": 1,
            },
        ),
        event_id="event-b",
    )
    projector.consume(first)
    projector.consume(second)

    with compatibility_event_projector_scope(projector):
        delayed: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(model_name="b", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        released: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(model_name="a", status=ExecutionStatus.SUCCESS),
            plan=None,
        )

    assert delayed == ""
    assert released is not None
    names: tuple[str, ...] = tuple(
        json.loads(line)["asset"]["name"] for line in released.splitlines()
    )
    assert names == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("canonical projection preserves final v1 bytes", True),),
    ids=lambda case: case.description,
)
def test_given_equivalent_terminal_when_formatting_final_json_then_v1_bytes_are_unchanged(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    result: BuildExecutionResult = BuildExecutionResult(
        status=BuildStatus.SUCCESS,
        model_results=(
            ModelExecutionResult(
                model_name="orders",
                status=ExecutionStatus.SUCCESS,
                duration_ms=42,
                promoted_relation="analytics.orders",
            ),
        ),
    )
    plan: PlanOutput = build_plan_output(model_entries=(build_model_entry(name="orders"),))
    legacy: str = format_build_execution_json(result=result, plan=plan)
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    projector.consume(
        lifecycle_event(
            "resource_attempt_completed",
            run_id="run-1",
            resource_id="model:orders",
            resource_attempt_id="attempt-1",
            payload={
                "resource_kind": "model",
                "resource_name": "orders",
                "attempt_number": 1,
                "duration_ms": 42,
            },
        )
    )

    with compatibility_event_projector_scope(projector):
        projected: str = format_build_execution_json(result=result, plan=plan)

    assert (projected == legacy) is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (
        PythonCheckProjectionTestCase(
            description="completed Python check preserves v1 check schema",
            event_type="resource_attempt_completed",
            passed=True,
            severity="error",
            payload={
                "resource_kind": "check",
                "resource_name": "quality_gate",
                "attempt_number": 1,
                "duration_ms": 5,
            },
            expected_status="pass",
        ),
        PythonCheckProjectionTestCase(
            description="failed Python check preserves v1 check schema",
            event_type="resource_attempt_failed",
            passed=False,
            severity="error",
            payload={
                "resource_kind": "check",
                "resource_name": "quality_gate",
                "attempt_number": 1,
                "duration_ms": 5,
                "error_type": "CheckFailed",
            },
            expected_status="fail",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_python_check_terminal_when_projecting_then_command_and_check_schema_are_preserved(
    test_case: PythonCheckProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    projector.consume(
        lifecycle_event(
            test_case.event_type,
            run_id="run-1",
            resource_id="check:quality_gate",
            resource_attempt_id="check-attempt",
            payload=test_case.payload,
        )
    )

    with compatibility_event_projector_scope(projector):
        encoded: str | None = format_build_item_execution_event(
            result=PythonCheckExecutionResult(
                node_name="quality_gate",
                passed=test_case.passed,
                severity=PythonCheckSeverity(test_case.severity),
                message="checked",
            ),
            plan=None,
            command="check",
        )

    assert encoded is not None
    record: dict[str, object] = json.loads(encoded)
    assert record["command"] == "check"
    assert record["event"] == "check"
    assert record["check"] == {
        "kind": "python_check",
        "name": "quality_gate",
        "check_id": "python_check:quality_gate",
        "passed": test_case.passed,
        "status": test_case.expected_status,
        "severity": test_case.severity,
        "message": "checked",
        "metadata": {},
    }


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("canonical-only terminal is omitted at finalization", "b"),),
    ids=lambda case: case.description,
)
def test_given_unrelated_terminal_before_check_when_finalizing_then_check_is_released(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    source: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_completed",
            run_id="run-1",
            resource_id="source:a",
            resource_attempt_id="source-attempt",
            payload={
                "resource_kind": "source",
                "resource_name": "a",
                "attempt_number": 1,
                "duration_ms": 1,
            },
        ),
        event_id="source-event",
    )
    check: LifecycleEvent = replace(
        lifecycle_event(
            "resource_attempt_completed",
            run_id="run-1",
            resource_id="model:b",
            resource_attempt_id="model-attempt",
            payload={
                "resource_kind": "model",
                "resource_name": "b",
                "attempt_number": 1,
                "duration_ms": 1,
            },
        ),
        event_id="model-event",
    )
    projector.consume(source)
    projector.consume(check)

    with compatibility_event_projector_scope(projector):
        delayed: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(model_name="b", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        finalized: str = projector.finalize_v1()

    assert delayed == ""
    assert json.loads(finalized)["asset"]["name"] == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("retry emits only final attempt", 9),),
    ids=lambda case: case.description,
)
def test_given_retry_terminals_when_final_result_arrives_then_only_latest_attempt_is_emitted(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    for number in (1, 2):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id="model:orders",
                    resource_attempt_id=f"attempt-{number}",
                    payload={
                        "resource_kind": "model",
                        "resource_name": "orders",
                        "attempt_number": number,
                        "duration_ms": number + 7,
                    },
                ),
                event_id=f"event-{number}",
            )
        )

    with compatibility_event_projector_scope(projector):
        encoded: str | None = format_build_item_execution_event(
            result=ModelExecutionResult(model_name="orders", status=ExecutionStatus.SUCCESS),
            plan=None,
        )

    assert encoded is not None
    assert len(encoded.splitlines()) == 1
    assert json.loads(encoded)["asset"]["duration_ms"] == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (
        CompatibilityProjectionTestCase(
            "writer race emits canonical bytes and closes once", ("a", "b")
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_coordinated_reverse_writer_race_when_closing_then_bytes_follow_canonical_order(
    tmp_path: Path,
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    for name in ("a", "b"):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=f"model:{name}",
                    resource_attempt_id=f"attempt-{name}",
                    payload={
                        "resource_kind": "model",
                        "resource_name": name,
                        "attempt_number": 1,
                        "duration_ms": 1,
                    },
                ),
                event_id=f"event-{name}",
            )
        )
    event_path: Path = tmp_path / "events.jsonl"
    writer: ExecutionEventWriter = ExecutionEventWriter(path=event_path)
    second_written: Event = Event()

    def write_second() -> None:
        with compatibility_event_projector_scope(projector):
            writer.write_build_result(
                result=ModelExecutionResult(model_name="b", status=ExecutionStatus.SUCCESS),
                plan=None,
            )
        second_written.set()

    def write_first() -> None:
        _ = second_written.wait(timeout=5)
        with compatibility_event_projector_scope(projector):
            writer.write_build_result(
                result=ModelExecutionResult(model_name="a", status=ExecutionStatus.SUCCESS),
                plan=None,
            )

    second_thread: Thread = Thread(target=write_second)
    first_thread: Thread = Thread(target=write_first)
    first_thread.start()
    second_thread.start()
    first_thread.join()
    second_thread.join()
    with compatibility_event_projector_scope(projector):
        writer.close()
        writer.close()

    names: tuple[str, ...] = tuple(
        json.loads(line)["asset"]["name"]
        for line in event_path.read_text(encoding="utf-8").splitlines()
    )
    assert names == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("last overlapping writer owns finalization", ("a", "b")),),
    ids=lambda case: case.description,
)
def test_given_overlapping_writers_when_first_closes_then_second_can_release_delayed_rows(
    tmp_path: Path,
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    for name in ("a", "b"):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=f"model:{name}",
                    resource_attempt_id=f"attempt-{name}",
                    payload={
                        "resource_kind": "model",
                        "resource_name": name,
                        "attempt_number": 1,
                        "duration_ms": 1,
                    },
                ),
                event_id=f"event-{name}",
            )
        )
    event_path: Path = tmp_path / "events.jsonl"
    with compatibility_event_projector_scope(projector):
        first_writer: ExecutionEventWriter = ExecutionEventWriter(path=event_path)
        second_writer: ExecutionEventWriter = ExecutionEventWriter(path=event_path)
        first_writer.write_build_result(
            result=ModelExecutionResult(model_name="b", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        first_writer.close()
        second_writer.write_build_result(
            result=ModelExecutionResult(model_name="a", status=ExecutionStatus.SUCCESS),
            plan=None,
        )
        second_writer.close()

    names: tuple[str, ...] = tuple(
        json.loads(line)["asset"]["name"]
        for line in event_path.read_text(encoding="utf-8").splitlines()
    )
    assert names == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("shared writer lock preserves physical order", ("a", "b")),),
    ids=lambda case: case.description,
)
def test_given_two_writers_when_first_pauses_after_projection_then_second_waits_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    for name in ("a", "b"):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=f"model:{name}",
                    resource_attempt_id=f"attempt-{name}",
                    payload={
                        "resource_kind": "model",
                        "resource_name": name,
                        "attempt_number": 1,
                        "duration_ms": 1,
                    },
                ),
                event_id=f"event-{name}",
            )
        )
    event_path: Path = tmp_path / "events.jsonl"
    with compatibility_event_projector_scope(projector):
        first_writer: ExecutionEventWriter = ExecutionEventWriter(path=event_path)
        second_writer: ExecutionEventWriter = ExecutionEventWriter(path=event_path)
    first_projected: Event = Event()
    release_first_write: Event = Event()
    second_attempting: Event = Event()
    second_finished: Event = Event()
    original_write: Callable[[str | None], None] = first_writer._write_payload

    def pause_first_write(payload: str | None) -> None:
        first_projected.set()
        _ = release_first_write.wait(timeout=5)
        original_write(payload)

    monkeypatch.setattr(first_writer, "_write_payload", pause_first_write)

    def write_first() -> None:
        with compatibility_event_projector_scope(projector):
            first_writer.write_build_result(
                result=ModelExecutionResult(model_name="a", status=ExecutionStatus.SUCCESS),
                plan=None,
            )

    def write_second() -> None:
        second_attempting.set()
        with compatibility_event_projector_scope(projector):
            second_writer.write_build_result(
                result=ModelExecutionResult(model_name="b", status=ExecutionStatus.SUCCESS),
                plan=None,
            )
        second_finished.set()

    first_thread: Thread = Thread(target=write_first)
    second_thread: Thread = Thread(target=write_second)
    first_thread.start()
    assert first_projected.wait(timeout=5)
    second_thread.start()
    assert second_attempting.wait(timeout=5)
    assert second_finished.wait(timeout=0.1) is False
    release_first_write.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)
    first_writer.close()
    second_writer.close()

    names: tuple[str, ...] = tuple(
        json.loads(line)["asset"]["name"]
        for line in event_path.read_text(encoding="utf-8").splitlines()
    )
    assert names == test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("distinct writer paths are rejected", True),),
    ids=lambda case: case.description,
)
def test_given_active_projector_when_writers_use_distinct_paths_then_side_channel_is_rejected(
    tmp_path: Path,
    test_case: CompatibilityProjectionTestCase,
) -> None:
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    with compatibility_event_projector_scope(projector):
        writer: ExecutionEventWriter = ExecutionEventWriter(path=tmp_path / "a.jsonl")
        with pytest.raises(ValueError, match="must share one output path"):
            _ = ExecutionEventWriter(path=tmp_path / "b.jsonl")
        writer.close()
    assert ((tmp_path / "b.jsonl").exists() is False) is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("audit terminal gates final check and summary", True),),
    ids=lambda case: case.description,
)
def test_given_only_run_terminal_then_matching_audit_terminal_when_formatting_build_json_then_gate_is_exact(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    audit: AuditExecutionResult = build_audit_result(
        name="orders_not_null",
        outcome=AuditOutcome.PASS,
        target_name="orders",
    )
    result: BuildExecutionResult = BuildExecutionResult(
        status=BuildStatus.SUCCESS,
        source_audit_results=(audit,),
        success_count=1,
    )
    plan: PlanOutput = build_plan_output()
    legacy: str = format_build_execution_json(result=result, plan=plan)
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    projector.consume(
        lifecycle_event(
            "run_completed",
            run_id="run-1",
            payload={
                "run_kind": "build",
                "duration_ms": 5,
                "succeeded_count": 1,
                "failed_count": 0,
                "skipped_count": 0,
            },
        )
    )
    with compatibility_event_projector_scope(projector):
        without_audit: dict[str, object] = json.loads(
            format_build_execution_json(result=result, plan=plan)
        )
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_completed",
                run_id="run-1",
                resource_id=audit_resource_id(
                    audit_name=audit.audit_name,
                    attachment_kind=audit.attachment_kind,
                    attached_target_name=audit.attached_target_name,
                    attached_column_name=audit.attached_column_name,
                ),
                resource_attempt_id="audit-attempt",
                payload={
                    "resource_kind": "audit",
                    "resource_name": audit.audit_name,
                    "attempt_number": 1,
                    "duration_ms": 1,
                },
            ),
            event_id="audit-event",
        )
    )
    with compatibility_event_projector_scope(projector):
        with_audit: str = format_build_execution_json(result=result, plan=plan)

    assert without_audit["checks"] == []
    assert without_audit["summary"] == {
        "success_count": 0,
        "failure_count": 0,
        "skipped_count": 0,
        "warning_count": 0,
        "python_check_pass_count": 0,
        "python_check_warn_count": 0,
        "python_check_fail_count": 0,
    }
    assert (with_audit == legacy) is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("typed retained aggregation preserves legacy rules", True),),
    ids=lambda case: case.description,
)
def test_given_partial_build_terminals_when_formatting_then_typed_summary_and_schema_are_preserved(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    model_audit: AuditExecutionResult = build_audit_result(
        name="model_warn", outcome=AuditOutcome.WARN, target_name="orders"
    )
    source_audit: AuditExecutionResult = build_audit_result(
        name="source_warn", outcome=AuditOutcome.WARN, target_name="raw_orders"
    )
    end_audit: AuditExecutionResult = build_audit_result(
        name="end_error", outcome=AuditOutcome.ERROR, target_name="orders"
    )
    model_results: tuple[ModelExecutionResult, ...] = (
        ModelExecutionResult(
            model_name="orders",
            status=ExecutionStatus.SUCCESS,
            duration_ms=10,
            warning_messages=("model warning",),
            audit_results=(model_audit,),
        ),
        ModelExecutionResult(
            model_name="freshness_blocked",
            status=ExecutionStatus.SKIPPED,
            duration_ms=10,
            error_code=BUILD_SOURCE_FRESHNESS_BLOCKED_CODE,
        ),
    )
    seed_results: tuple[SeedExecutionResult, ...] = (
        SeedExecutionResult(seed_name="countries", status=ExecutionStatus.SUCCESS, duration_ms=10),
        SeedExecutionResult(seed_name="filtered", status=ExecutionStatus.SUCCESS, duration_ms=10),
    )
    function_results: tuple[FunctionExecutionResult, ...] = (
        FunctionExecutionResult(
            function_name="normalize",
            function_kind="udf",
            status=ExecutionStatus.SUCCESS,
            duration_ms=10,
            warning_messages=("function warning",),
        ),
    )
    load_results: tuple[LoadExecutionResult, ...] = (
        LoadExecutionResult(
            source_name="raw_orders",
            loader_name="load_orders",
            status=ExecutionStatus.SUCCESS,
            target="raw.orders",
            duration_ms=10,
        ),
    )
    test_results: tuple[SqlTestExecutionResult, ...] = (
        SqlTestExecutionResult(test_name="orders_test", outcome=SqlTestOutcome.PASS),
    )
    result: BuildExecutionResult = aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=test_results,
        source_audit_results=(source_audit,),
        end_audit_results=(end_audit,),
    )
    python_nodes: tuple[PythonNodeExecutionResult, ...] = (
        PythonNodeExecutionResult(
            node_name="publish", kind=PythonNodeKind.ASSET, status=PythonNodeStatus.SUCCESS
        ),
    )
    python_checks: tuple[PythonCheckExecutionResult, ...] = (
        PythonCheckExecutionResult(
            node_name="quality", passed=False, severity=PythonCheckSeverity.WARN
        ),
    )
    terminal_identities: tuple[tuple[str, str, str], ...] = (
        ("model:orders", "model", "orders"),
        ("model:freshness_blocked", "model", "freshness_blocked"),
        ("seed:countries", "seed", "countries"),
        ("udf:normalize", "udf", "normalize"),
        ("source:raw_orders", "source", "raw_orders"),
        ("sql_test:orders_test", "sql_test", "orders_test"),
        ("asset:publish", "asset", "publish"),
        ("check:quality", "check", "quality"),
        (
            audit_resource_id(
                audit_name=source_audit.audit_name,
                attachment_kind=source_audit.attachment_kind,
                attached_target_name=source_audit.attached_target_name,
                attached_column_name=source_audit.attached_column_name,
            ),
            "audit",
            source_audit.audit_name,
        ),
        (
            audit_resource_id(
                audit_name=end_audit.audit_name,
                attachment_kind=end_audit.attachment_kind,
                attached_target_name=end_audit.attached_target_name,
                attached_column_name=end_audit.attached_column_name,
            ),
            "audit",
            end_audit.audit_name,
        ),
    )
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    for index, (resource_id, resource_kind, resource_name) in enumerate(terminal_identities):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=resource_id,
                    resource_attempt_id=f"attempt-{index}",
                    payload={
                        "resource_kind": resource_kind,
                        "resource_name": resource_name,
                        "attempt_number": 1,
                        "duration_ms": 10,
                    },
                ),
                event_id=f"event-{index}",
            )
        )

    with compatibility_event_projector_scope(projector):
        partial: dict[str, object] = json.loads(
            format_build_execution_json(
                result=result,
                plan=build_plan_output(),
                python_node_results=python_nodes,
                python_check_results=python_checks,
            )
        )

    assert partial["summary"] == {
        "success_count": 6,
        "failure_count": 1,
        "skipped_count": 1,
        "warning_count": 5,
        "python_check_pass_count": 0,
        "python_check_warn_count": 1,
        "python_check_fail_count": 0,
    }
    assert len(partial["assets"]) == 6  # type: ignore[arg-type]
    assert len(partial["checks"]) == 5  # type: ignore[arg-type]
    assert "filtered" not in json.dumps(partial["assets"])

    legacy: str = format_build_execution_json(
        result=result,
        plan=build_plan_output(),
        python_node_results=python_nodes,
        python_check_results=python_checks,
    )
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_completed",
                run_id="run-1",
                resource_id="seed:filtered",
                resource_attempt_id="attempt-filtered",
                payload={
                    "resource_kind": "seed",
                    "resource_name": "filtered",
                    "attempt_number": 1,
                    "duration_ms": 10,
                },
            ),
            event_id="event-filtered",
        )
    )
    with compatibility_event_projector_scope(projector):
        complete: str = format_build_execution_json(
            result=result,
            plan=build_plan_output(),
            python_node_results=python_nodes,
            python_check_results=python_checks,
        )
    assert (complete == legacy) is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (
        CompatibilityProjectionTestCase(
            "typed partial run aggregation preserves legacy rules", True
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_partial_run_terminals_when_formatting_then_typed_summary_and_schema_are_preserved(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    model_results: tuple[ModelExecutionResult, ...] = (
        ModelExecutionResult(
            model_name="orders",
            status=ExecutionStatus.SUCCESS,
            duration_ms=10,
            warning_messages=("model warning",),
            audit_results=(
                build_audit_result(
                    name="model_warn", outcome=AuditOutcome.WARN, target_name="orders"
                ),
            ),
        ),
        ModelExecutionResult(
            model_name="freshness_blocked",
            status=ExecutionStatus.SKIPPED,
            duration_ms=10,
            error_code=BUILD_SOURCE_FRESHNESS_BLOCKED_CODE,
        ),
    )
    seed_results: tuple[SeedExecutionResult, ...] = (
        SeedExecutionResult(seed_name="countries", status=ExecutionStatus.SUCCESS, duration_ms=10),
        SeedExecutionResult(seed_name="filtered", status=ExecutionStatus.SUCCESS, duration_ms=10),
    )
    function_results: tuple[FunctionExecutionResult, ...] = (
        FunctionExecutionResult(
            function_name="normalize",
            function_kind="udf",
            status=ExecutionStatus.SUCCESS,
            duration_ms=10,
            warning_messages=("function warning",),
        ),
    )
    load_results: tuple[LoadExecutionResult, ...] = (
        LoadExecutionResult(
            source_name="raw_orders",
            loader_name="load_orders",
            status=ExecutionStatus.SUCCESS,
            target="raw.orders",
            duration_ms=10,
        ),
    )
    result: BuildExecutionResult = aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        function_results=function_results,
        load_results=load_results,
        test_results=(),
        source_audit_results=(),
        end_audit_results=(),
    )
    python_nodes: tuple[PythonNodeExecutionResult, ...] = (
        PythonNodeExecutionResult(
            node_name="publish", kind=PythonNodeKind.ASSET, status=PythonNodeStatus.SUCCESS
        ),
    )
    terminal_identities: tuple[tuple[str, str, str], ...] = (
        ("model:orders", "model", "orders"),
        ("model:freshness_blocked", "model", "freshness_blocked"),
        ("seed:countries", "seed", "countries"),
        ("udf:normalize", "udf", "normalize"),
        ("source:raw_orders", "source", "raw_orders"),
        ("asset:publish", "asset", "publish"),
    )
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    for index, (resource_id, resource_kind, resource_name) in enumerate(terminal_identities):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="run-1",
                    resource_id=resource_id,
                    resource_attempt_id=f"run-attempt-{index}",
                    payload={
                        "resource_kind": resource_kind,
                        "resource_name": resource_name,
                        "attempt_number": 1,
                        "duration_ms": 10,
                    },
                ),
                event_id=f"run-event-{index}",
            )
        )

    with compatibility_event_projector_scope(projector):
        partial: dict[str, object] = json.loads(
            format_run_execution_json(
                result=result,
                plan=build_plan_output(),
                python_node_results=python_nodes,
            )
        )
    assert partial["summary"] == {
        "success_count": 5,
        "failure_count": 1,
        "skipped_count": 1,
        "warning_count": 3,
    }
    assert len(partial["assets"]) == 6  # type: ignore[arg-type]
    assert "filtered" not in json.dumps(partial["assets"])

    legacy: str = format_run_execution_json(
        result=result,
        plan=build_plan_output(),
        python_node_results=python_nodes,
    )
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_completed",
                run_id="run-1",
                resource_id="seed:filtered",
                resource_attempt_id="run-attempt-filtered",
                payload={
                    "resource_kind": "seed",
                    "resource_name": "filtered",
                    "attempt_number": 1,
                    "duration_ms": 10,
                },
            ),
            event_id="run-event-filtered",
        )
    )
    with compatibility_event_projector_scope(projector):
        complete: str = format_run_execution_json(
            result=result,
            plan=build_plan_output(),
            python_node_results=python_nodes,
        )
    assert (complete == legacy) is test_case.expected_output


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("scenario identities isolate repeated resources", (11, 22)),),
    ids=lambda case: case.description,
)
def test_given_repeated_scenario_resources_when_formatting_then_each_uses_its_qualified_terminal(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    results: tuple[ScenarioRunResult, ...] = (
        ScenarioRunResult(
            scenario_name="first",
            status=ExecutionStatus.SUCCESS,
            seed_results=(
                SeedExecutionResult(seed_name="shared_seed", status=ExecutionStatus.SUCCESS),
            ),
            function_results=(
                FunctionExecutionResult(
                    function_name="shared_function",
                    function_kind="udf",
                    status=ExecutionStatus.SUCCESS,
                ),
            ),
            model_results=(
                ModelExecutionResult(model_name="shared_model", status=ExecutionStatus.SUCCESS),
            ),
        ),
        ScenarioRunResult(
            scenario_name="second",
            status=ExecutionStatus.SUCCESS,
            seed_results=(
                SeedExecutionResult(seed_name="shared_seed", status=ExecutionStatus.SUCCESS),
            ),
            function_results=(
                FunctionExecutionResult(
                    function_name="shared_function",
                    function_kind="udf",
                    status=ExecutionStatus.SUCCESS,
                ),
            ),
            model_results=(
                ModelExecutionResult(model_name="shared_model", status=ExecutionStatus.SUCCESS),
            ),
        ),
    )
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    scenario_terminals: tuple[tuple[str, str, str, int], ...] = (
        ("sql_scenario:first", "scenario", "first", 1),
        ("sql_scenario:second", "scenario", "second", 1),
        ("scenario:first:model:shared_model", "model", "shared_model", 11),
        ("scenario:second:model:shared_model", "model", "shared_model", 22),
        ("scenario:first:seed:shared_seed", "seed", "shared_seed", 33),
        ("scenario:first:udf:shared_function", "udf", "shared_function", 44),
    )
    for index, (resource_id, resource_kind, resource_name, duration_ms) in enumerate(
        scenario_terminals
    ):
        projector.consume(
            replace(
                lifecycle_event(
                    "resource_attempt_completed",
                    run_id="scenario-run",
                    resource_id=resource_id,
                    resource_attempt_id=f"scenario-attempt-{index}",
                    payload={
                        "resource_kind": resource_kind,
                        "resource_name": resource_name,
                        "attempt_number": 1,
                        "duration_ms": duration_ms,
                    },
                ),
                event_id=f"scenario-event-{index}",
            )
        )

    with compatibility_event_projector_scope(projector):
        payload: dict[str, object] = json.loads(format_scenario_execution_json(results=results))

    assets: list[dict[str, object]] = payload["assets"]  # type: ignore[assignment]
    model_durations: tuple[object, ...] = (assets[2]["duration_ms"], assets[3]["duration_ms"])
    assert model_durations == test_case.expected_output
    assert tuple(asset["kind"] for asset in assets) == ("seed", "udf", "model", "model")
    assert tuple(asset["duration_ms"] for asset in assets) == (33, 44, 11, 22)


@pytest.mark.parametrize(
    "test_case",
    (CompatibilityProjectionTestCase("scenario terminal gates exact result membership", True),),
    ids=lambda case: case.description,
)
def test_given_success_failure_and_missing_scenario_terminals_when_formatting_then_only_exact_matches_remain(
    test_case: CompatibilityProjectionTestCase,
) -> None:
    results: tuple[ScenarioRunResult, ...] = (
        ScenarioRunResult(scenario_name="passing", status=ExecutionStatus.SUCCESS),
        ScenarioRunResult(scenario_name="failing", status=ExecutionStatus.FAILED),
        ScenarioRunResult(scenario_name="missing", status=ExecutionStatus.FAILED),
    )
    legacy: dict[str, object] = json.loads(format_scenario_execution_json(results=results))
    projector: CompatibilityEventProjector = CompatibilityEventProjector()
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_completed",
                run_id="scenario-run",
                resource_id="sql_scenario:passing",
                resource_attempt_id="passing-attempt",
                payload={
                    "resource_kind": "scenario",
                    "resource_name": "passing",
                    "attempt_number": 1,
                    "duration_ms": 1,
                },
            ),
            event_id="passing-event",
        )
    )
    projector.consume(
        replace(
            lifecycle_event(
                "resource_attempt_failed",
                run_id="scenario-run",
                resource_id="sql_scenario:failing",
                resource_attempt_id="failing-attempt",
                payload={
                    "resource_kind": "scenario",
                    "resource_name": "failing",
                    "attempt_number": 1,
                    "duration_ms": 1,
                    "error_type": "ExecutionFailed",
                },
            ),
            event_id="failing-event",
        )
    )

    with compatibility_event_projector_scope(projector):
        projected: dict[str, object] = json.loads(format_scenario_execution_json(results=results))

    checks: list[dict[str, object]] = projected["checks"]  # type: ignore[assignment]
    scenarios: list[dict[str, object]] = projected["scenarios"]  # type: ignore[assignment]
    assert projected["status"] == "failed"
    assert projected["summary"] == {"pass_count": 1, "fail_count": 1, "total_count": 2}
    assert tuple(check["name"] for check in checks) == ("passing", "failing")
    assert tuple(scenario["name"] for scenario in scenarios) == ("passing", "failing")
    assert legacy["summary"] == {"pass_count": 1, "fail_count": 2, "total_count": 3}
    assert (projected["assets"] == []) is test_case.expected_output
