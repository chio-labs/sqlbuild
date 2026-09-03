"""Tests for standalone audit pipeline lifecycle ordering."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from itertools import chain, repeat
from pathlib import Path
from typing import Any, cast
from unittest.mock import DEFAULT, Mock

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.progress.classes.audit_progress_reporter import AuditProgressReporter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind, CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.cost._helpers.ledger import read_statement_ledger, record_statement
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.models import CostResourceContext, StatementLedgerEntry
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline._helpers import auditing
from sqlbuild.executor.pipeline.exceptions import AuditOutcomeError
from sqlbuild.executor.pipeline.main.run import run_audit_pipeline
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers._test_types import (
    AuditConcurrencyTestCase,
    AuditLogicalIdentityTestCase,
    AuditPipelineLifecycleTestCase,
    AuditResourceIdentityTestCase,
)
from tests.unit.src.sqlbuild.executor.pipeline._helpers.helpers import (
    audit_entry,
    audit_result,
    lifecycle_events_with_prefix,
    lifecycle_order_with_prefix,
)


class _InterruptingCompletionQueue(queue.Queue[Any]):
    def __init__(self) -> None:
        super().__init__()
        self._get_delegate: Mock = Mock(
            wraps=super().get,
            side_effect=chain((DEFAULT, KeyboardInterrupt), repeat(DEFAULT)),
        )

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        return self._get_delegate(block, timeout)


class _AuditQueueFactory:
    def __init__(self) -> None:
        self._queues = iter((queue.Queue(), _InterruptingCompletionQueue()))

    def __call__(self) -> queue.Queue[Any]:
        return next(self._queues)


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
    assert events[-2].event_type == test_case.expected_event_type
    assert events[-1].event_type == "run_completed"
    assert events[-1].payload["warn_count"] == 1
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


@pytest.mark.parametrize(
    "test_case",
    (
        AuditLogicalIdentityTestCase(
            description="end-scheduled model audit retains logical target identity",
            expected_id="audit:cross_model_consistency:model:orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_end_scheduled_attached_audit_when_formatted_then_logical_target_defines_identity(
    test_case: AuditLogicalIdentityTestCase,
) -> None:
    resource_id: str = audit_resource_id(
        audit_name="cross_model_consistency",
        attachment_kind=AuditAttachmentKind.END,
        attached_target_kind=AttachedAuditTargetKind.MODEL,
        attached_target_name="orders",
        attached_column_name=None,
    )

    assert resource_id == test_case.expected_id


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="empty plan", expected_count=0),),
    ids=lambda case: case.description,
)
def test_given_empty_audit_plan_when_run_concurrently_then_opens_no_connections(
    test_case: AuditConcurrencyTestCase,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)

    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=PlanOutput(),
        connection_config={},
        adapter=adapter,
        max_concurrency=8,
    )

    assert len(results) == test_case.expected_count
    adapter.connect.assert_not_called()
    adapter.close.assert_not_called()


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="reversed completion", expected_names=("first", "second", "third")
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_reversed_completion_when_run_concurrently_then_results_remain_plan_ordered(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: tuple[AuditPlanEntry, ...] = tuple(
        audit_entry(name) for name in test_case.expected_names
    )
    connections: tuple[object, ...] = (object(), object())
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = connections
    active_connections: set[int] = set()
    lock: threading.Lock = threading.Lock()
    maximum_active: list[int] = [0]
    completion_order: list[str] = []
    callback_order: list[str] = []

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        connection: object = kwargs["connection"]
        assert isinstance(entry, AuditPlanEntry)
        connection_id: int = id(connection)
        with lock:
            assert connection_id not in active_connections
            active_connections.add(connection_id)
            maximum_active[0] = max(maximum_active[0], len(active_connections))
        time.sleep({"first": 0.08, "second": 0.02, "third": 0.01}[entry.name])
        with lock:
            active_connections.remove(connection_id)
            completion_order.append(entry.name)
        return audit_result(entry.name)

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)

    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=PlanOutput(audit_entries=entries),
        connection_config={},
        adapter=adapter,
        max_concurrency=2,
        on_audit_complete=lambda result: callback_order.append(result.audit_name),
    )

    assert tuple(result.audit_name for result in results) == test_case.expected_names
    assert completion_order == ["second", "third", "first"]
    assert tuple(callback_order) == test_case.expected_names
    assert maximum_active[0] == 2
    assert adapter.connect.call_count == 2
    assert adapter.close.call_count == 2


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="multiple errors", expected_error="failure-first"),),
    ids=lambda case: case.description,
)
def test_given_multiple_worker_errors_when_run_then_earliest_plan_error_is_raised_after_drain(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: tuple[AuditPlanEntry, ...] = tuple(
        audit_entry(name) for name in ("first", "second", "never_started")
    )
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    started: list[str] = []
    finished: list[str] = []
    lock: threading.Lock = threading.Lock()

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        with lock:
            started.append(entry.name)
        time.sleep({"first": 0.06, "second": 0.01}[entry.name])
        with lock:
            finished.append(entry.name)
        raise RuntimeError(f"failure-{entry.name}")

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)

    with pytest.raises(RuntimeError, match=test_case.expected_error):
        run_audit_pipeline(
            plan=PlanOutput(audit_entries=entries),
            connection_config={},
            adapter=adapter,
            max_concurrency=2,
        )

    assert set(started) == {"first", "second"}
    assert set(finished) == {"first", "second"}
    assert adapter.close.call_count == 2


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="keyboard interrupt", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_worker_keyboard_interrupt_when_run_then_stops_submission_and_closes_after_drain(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: tuple[AuditPlanEntry, ...] = tuple(
        audit_entry(name) for name in ("interrupt", "running", "never_started")
    )
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    finished_running: threading.Event = threading.Event()
    actions: dict[str, Callable[[], object]] = {
        "interrupt": Mock(side_effect=KeyboardInterrupt),
        "running": finished_running.set,
    }

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        time.sleep({"interrupt": 0.01, "running": 0.05}[entry.name])
        actions[entry.name]()
        return audit_result(entry.name)

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)

    with pytest.raises(KeyboardInterrupt):
        run_audit_pipeline(
            plan=PlanOutput(audit_entries=entries),
            connection_config={},
            adapter=adapter,
            max_concurrency=2,
        )

    assert finished_running.is_set()
    assert adapter.close.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="serial concurrent equivalence",
            expected_names=("passing", "warning", "error"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_file_backed_duckdb_audits_when_run_serial_and_concurrent_then_results_are_equivalent(
    test_case: AuditConcurrencyTestCase,
    tmp_path: Path,
) -> None:
    entries: tuple[AuditPlanEntry, ...] = (
        audit_entry(test_case.expected_names[0], sql="SELECT 1 WHERE FALSE"),
        audit_entry(test_case.expected_names[1], sql="SELECT 1", severity=AuditSeverity.WARN),
        audit_entry(test_case.expected_names[2], sql="SELECT 1"),
    )
    plan: PlanOutput = PlanOutput(audit_entries=entries)
    connection_config: dict[str, object] = {"database": str(tmp_path / "concurrent.duckdb")}

    serial: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=plan,
        connection_config=connection_config,
        adapter=DuckDbAdapter(),
        max_concurrency=1,
    )
    concurrent: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=plan,
        connection_config=connection_config,
        adapter=DuckDbAdapter(),
        max_concurrency=2,
    )

    assert concurrent == serial
    assert tuple(result.outcome for result in concurrent) == (
        AuditOutcome.PASS,
        AuditOutcome.WARN,
        AuditOutcome.ERROR,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="non tty ordered aggregate progress",
            expected_names=("first", "second"),
            expected_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_reversed_completions_when_reporting_non_tty_then_rows_and_enrichment_are_ordered(
    test_case: AuditConcurrencyTestCase,
) -> None:
    entries: tuple[AuditPlanEntry, ...] = tuple(map(audit_entry, test_case.expected_names))
    stream: StringIO = StringIO()
    enriched: list[str] = []
    reporter: AuditProgressReporter = AuditProgressReporter(
        entries=entries,
        worker_limit=test_case.expected_count,
        stream=stream,
        use_color=False,
    )
    reporter.set_result_callback(lambda result: enriched.append(result.audit_name))

    reporter.on_item_start(entries[0])
    reporter.on_item_start(entries[1])
    reporter.on_item_complete(audit_result("second"))
    reporter.on_item_complete(audit_result("first"))

    assert stream.getvalue().index("first") < stream.getvalue().index("second")
    assert tuple(enriched) == test_case.expected_names


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="connection callback cleanup", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_open_connections_when_connection_callback_raises_then_all_close_once_and_error_wins(
    test_case: AuditConcurrencyTestCase,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    adapter.close.side_effect = RuntimeError("close failure")

    with pytest.raises(LookupError, match="callback failure"):
        run_audit_pipeline(
            plan=PlanOutput(audit_entries=(audit_entry("first"), audit_entry("second"))),
            connection_config={},
            adapter=adapter,
            max_concurrency=2,
            on_connection_complete=Mock(side_effect=LookupError("callback failure")),
        )

    assert adapter.close.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="partial open cleanup", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_partial_connection_open_when_later_open_fails_then_opened_connection_closes_once(
    test_case: AuditConcurrencyTestCase,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    opened: object = object()
    adapter.connect.side_effect = (opened, LookupError("open failure"))

    with pytest.raises(LookupError, match="open failure"):
        run_audit_pipeline(
            plan=PlanOutput(audit_entries=(audit_entry("first"), audit_entry("second"))),
            connection_config={},
            adapter=adapter,
            max_concurrency=2,
            on_connection_error=Mock(side_effect=RuntimeError("connection error callback")),
        )

    assert adapter.close.call_count == test_case.expected_count
    adapter.close.assert_called_once_with(opened)


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="execution error precedence", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_execution_and_close_errors_when_running_then_execution_error_wins(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.return_value = object()
    adapter.close.side_effect = RuntimeError("close failure")
    monkeypatch.setattr(auditing, "execute_audit", Mock(side_effect=LookupError("execute failure")))

    with pytest.raises(LookupError, match="execute failure"):
        run_audit_pipeline(
            plan=PlanOutput(audit_entries=(audit_entry("first"),)),
            connection_config={},
            adapter=adapter,
        )

    assert adapter.close.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="legacy keyword callbacks",
            expected_names=("first", "second"),
            expected_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_legacy_keyword_callbacks_when_running_default_serial_then_callbacks_remain_compatible(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.return_value = object()
    started: list[str] = []
    completed: list[str] = []
    connection_started: list[int] = []
    connection_completed: list[int] = []
    monkeypatch.setattr(
        auditing,
        "execute_audit",
        lambda **kwargs: audit_result(cast(AuditPlanEntry, kwargs["audit"]).name),
    )

    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=PlanOutput(
            audit_entries=tuple(audit_entry(name) for name in test_case.expected_names)
        ),
        connection_config={},
        adapter=adapter,
        on_connection_start=connection_started.append,
        on_connection_complete=lambda connection_count, elapsed_seconds: (
            connection_completed.append(connection_count)
        ),
        on_connection_error=Mock(),
        on_audit_start=lambda entry: started.append(entry.name),
        on_audit_complete=lambda result: completed.append(result.audit_name),
        run_id="legacy-run",
    )

    assert tuple(result.audit_name for result in results) == test_case.expected_names
    assert tuple(started) == test_case.expected_names
    assert tuple(completed) == test_case.expected_names
    assert connection_started == [test_case.expected_count]
    assert connection_completed == [test_case.expected_count]


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="inherited concurrent cost ledger",
            expected_names=("first", "second"),
            expected_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_outer_cost_ledger_when_runtime_dir_is_omitted_then_workers_inherit_valid_ledger(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    ledger_path: Path = tmp_path / "statements.jsonl"

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        with CostContext.resource_scope(resource_type="audit", resource_name=entry.name):
            context: CostResourceContext | None = CostContext.current()
            assert context is not None
            now: datetime = datetime.now(UTC)
            record_statement(
                context=context,
                statement_id=f"statement-{entry.name}",
                sql="SELECT 1",
                query_id=None,
                status="completed",
                started_at=now,
                completed_at=now,
            )
        return audit_result(entry.name)

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)
    with CostContext.scope(
        run_id="outer-run",
        resource_type="run",
        resource_name="outer",
        ledger_path=ledger_path,
    ):
        run_audit_pipeline(
            plan=PlanOutput(
                audit_entries=tuple(audit_entry(name) for name in test_case.expected_names)
            ),
            connection_config={},
            adapter=adapter,
            max_concurrency=2,
            run_id="audit-run",
        )

    ledger: tuple[StatementLedgerEntry, ...] = read_statement_ledger(
        path=ledger_path, run_id="audit-run"
    )
    assert len(ledger) == test_case.expected_count
    assert {entry.resource_name for entry in ledger} == set(test_case.expected_names)


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="unknown audit outcome", expected_count=1),),
    ids=lambda case: case.description,
)
def test_given_unknown_audit_outcome_when_aggregating_then_it_is_rejected_and_connection_closes(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.return_value = object()
    invalid: AuditExecutionResult = replace(
        audit_result("first"), outcome=cast(AuditOutcome, "unknown")
    )
    monkeypatch.setattr(auditing, "execute_audit", Mock(return_value=invalid))

    with pytest.raises(AuditOutcomeError, match="unknown audit outcome"):
        run_audit_pipeline(
            plan=PlanOutput(audit_entries=(audit_entry("first"),)),
            connection_config={},
            adapter=adapter,
        )

    assert adapter.close.call_count == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="unique concurrent attempts",
            expected_names=("first", "second", "third"),
            expected_count=3,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_concurrent_audits_when_lifecycle_publishes_then_attempts_are_unique_and_terminal_once(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    dispatcher: EventDispatcher = EventDispatcher()
    events: list[LifecycleEvent] = []
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    monkeypatch.setattr(
        auditing,
        "execute_audit",
        lambda **kwargs: audit_result(cast(AuditPlanEntry, kwargs["audit"]).name),
    )

    with invocation_scope("audit-invocation"), dispatcher_scope(dispatcher):
        run_audit_pipeline(
            plan=PlanOutput(
                audit_entries=tuple(audit_entry(name) for name in test_case.expected_names)
            ),
            connection_config={},
            adapter=adapter,
            max_concurrency=2,
            run_id="audit-run",
        )

    starts: list[LifecycleEvent] = list(
        filter(lambda event: event.event_type == "resource_attempt_started", events)
    )
    terminals: list[LifecycleEvent] = list(
        filter(
            lambda event: (
                event.event_type.startswith("resource_attempt_")
                and event.event_type != "resource_attempt_started"
            ),
            events,
        )
    )
    attempt_ids: set[str | None] = {event.resource_attempt_id for event in starts}
    assert len(starts) == test_case.expected_count
    assert len(terminals) == test_case.expected_count
    assert len(attempt_ids) == test_case.expected_count
    assert {event.resource_attempt_id for event in terminals} == attempt_ids


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="success before fatal",
            expected_names=("success",),
            expected_error="fatal-second",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_success_before_fatal_when_draining_then_success_projects_and_run_counts_it(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    completed: list[str] = []
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    actions: dict[str, Callable[[], AuditExecutionResult]] = {
        "success": lambda: audit_result("success"),
        "fatal": Mock(side_effect=RuntimeError(test_case.expected_error)),
    }

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        time.sleep({"success": 0.01, "fatal": 0.05}[entry.name])
        return actions[entry.name]()

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)
    with invocation_scope("audit-invocation"), dispatcher_scope(dispatcher):
        with pytest.raises(RuntimeError, match=test_case.expected_error):
            run_audit_pipeline(
                plan=PlanOutput(audit_entries=(audit_entry("success"), audit_entry("fatal"))),
                connection_config={},
                adapter=adapter,
                max_concurrency=2,
                on_audit_complete=lambda result: completed.append(result.audit_name),
            )

    terminal: LifecycleEvent = tuple(
        filter(lambda event: event.event_type == "run_failed", events)
    )[0]
    assert tuple(completed) == test_case.expected_names
    assert terminal.payload["pass_count"] == 1
    assert terminal.payload["warn_count"] == 0
    assert terminal.payload["fail_count"] == 0


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="fatal before drained success",
            expected_names=("later_success",),
            expected_error="fatal-first",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_fatal_before_later_started_success_when_draining_then_gap_allows_projection(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    completed: list[str] = []
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    actions: dict[str, Callable[[], AuditExecutionResult]] = {
        "fatal": Mock(side_effect=RuntimeError(test_case.expected_error)),
        "later_success": lambda: audit_result("later_success"),
    }

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        time.sleep({"fatal": 0.01, "later_success": 0.05}[entry.name])
        return actions[entry.name]()

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)
    with invocation_scope("audit-invocation"), dispatcher_scope(dispatcher):
        with pytest.raises(RuntimeError, match=test_case.expected_error):
            run_audit_pipeline(
                plan=PlanOutput(audit_entries=(audit_entry("fatal"), audit_entry("later_success"))),
                connection_config={},
                adapter=adapter,
                max_concurrency=2,
                on_audit_complete=lambda result: completed.append(result.audit_name),
            )

    terminal: LifecycleEvent = tuple(
        filter(lambda event: event.event_type == "run_failed", events)
    )[0]
    assert tuple(completed) == test_case.expected_names
    assert terminal.payload["pass_count"] == 1
    assert terminal.payload["warn_count"] == 0
    assert terminal.payload["fail_count"] == 0


@pytest.mark.parametrize(
    "test_case",
    (
        AuditConcurrencyTestCase(
            description="multiple failures with drained success",
            expected_names=("third_success",),
            expected_error="failure-first",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_multiple_failures_and_success_when_drained_then_earliest_error_and_ordered_projection(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object(), object())
    completed: list[str] = []
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    actions: dict[str, Callable[[], AuditExecutionResult]] = {
        "first": Mock(side_effect=RuntimeError(test_case.expected_error)),
        "second": Mock(side_effect=RuntimeError("failure-second")),
        "third_success": lambda: audit_result("third_success"),
    }

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        time.sleep({"first": 0.05, "second": 0.01, "third_success": 0.02}[entry.name])
        return actions[entry.name]()

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)
    with invocation_scope("audit-invocation"), dispatcher_scope(dispatcher):
        with pytest.raises(RuntimeError, match=test_case.expected_error):
            run_audit_pipeline(
                plan=PlanOutput(
                    audit_entries=(
                        audit_entry("first"),
                        audit_entry("second"),
                        audit_entry("third_success"),
                    )
                ),
                connection_config={},
                adapter=adapter,
                max_concurrency=3,
                on_audit_complete=lambda result: completed.append(result.audit_name),
            )

    terminal: LifecycleEvent = tuple(
        filter(lambda event: event.event_type == "run_failed", events)
    )[0]
    assert tuple(completed) == test_case.expected_names
    assert terminal.payload["pass_count"] == 1
    assert terminal.payload["warn_count"] == 0
    assert terminal.payload["fail_count"] == 0


@pytest.mark.parametrize(
    "test_case",
    (AuditConcurrencyTestCase(description="coordinator interrupt", expected_count=2),),
    ids=lambda case: case.description,
)
def test_given_coordinator_keyboard_interrupt_when_waiting_then_workers_drain_and_connections_close(
    test_case: AuditConcurrencyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: Mock = Mock(spec=BaseAdapter)
    adapter.connect.side_effect = (object(), object())
    started: list[str] = []
    finished: list[str] = []
    completed: list[str] = []
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    def execute_audit(**kwargs: object) -> AuditExecutionResult:
        entry: object = kwargs["audit"]
        assert isinstance(entry, AuditPlanEntry)
        started.append(entry.name)
        time.sleep({"first": 0.01, "second": 0.05}[entry.name])
        finished.append(entry.name)
        return audit_result(entry.name)

    monkeypatch.setattr(auditing, "execute_audit", execute_audit)
    monkeypatch.setattr(auditing.queue, "Queue", _AuditQueueFactory())

    with invocation_scope("audit-invocation"), dispatcher_scope(dispatcher):
        with pytest.raises(KeyboardInterrupt):
            run_audit_pipeline(
                plan=PlanOutput(audit_entries=(audit_entry("first"), audit_entry("second"))),
                connection_config={},
                adapter=adapter,
                max_concurrency=2,
                on_audit_complete=lambda result: completed.append(result.audit_name),
            )

    terminal: LifecycleEvent = tuple(
        filter(lambda event: event.event_type == "run_failed", events)
    )[0]
    assert set(started) == {"first", "second"}
    assert set(finished) == set(started)
    assert completed == ["first", "second"]
    assert terminal.payload["pass_count"] == test_case.expected_count
    assert terminal.payload["warn_count"] == 0
    assert terminal.payload["fail_count"] == 0
    assert adapter.close.call_count == test_case.expected_count
