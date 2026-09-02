from __future__ import annotations

from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.adapters.bigquery.classes.bigquery_connection import _BigQueryConnection
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    current_event_dispatcher,
    current_execution_identity,
    dispatcher_scope,
    invocation_scope,
    operation_scope,
)
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle
from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    ErrorCodePrivacyCase,
    StatementKindPrivacyCase,
    StatementLifecycleCase,
)


class _RecordingCursor:
    def __init__(self, events: list[LifecycleEvent]) -> None:
        self._events: list[LifecycleEvent] = events
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.rowcount = 2

    def execute(self, sql: str, parameters: tuple[str, ...]) -> _RecordingCursor:
        assert self._events[-1].event_type == "statement_started"
        self.calls.append((sql, (parameters,)))
        return self

    def executemany(self, sql: str, parameters: tuple[str, ...]) -> _RecordingCursor:
        assert self._events[-1].event_type == "statement_started"
        self.calls.append((sql, (parameters,)))
        return self


class _DirectCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.rowcount = -1

    def execute(self, sql: str, parameters: tuple[str, ...]) -> _DirectCursor:
        self.calls.append((sql, (parameters,)))
        return self


class _FailingCursor:
    rowcount: int = -1

    def execute(self, sql: str) -> Any:
        del sql
        raise LookupError("driver failure")


class _FailingSubscriber:
    def __call__(self, event: LifecycleEvent) -> None:
        del event
        raise RuntimeError("observer failure")


class _BigQueryRows:
    schema: tuple[object, ...] = ()

    def __iter__(self) -> Any:
        return iter(())


class _BigQueryJob:
    job_id: str = "job-current"

    def result(self) -> _BigQueryRows:
        return _BigQueryRows()


class _FailingBigQueryJob:
    job_id: str = "job-current"

    def result(self) -> _BigQueryRows:
        raise RuntimeError("private failure")


class _BigQueryClient:
    def __init__(self, job: Any, events: list[LifecycleEvent]) -> None:
        self._job: Any = job
        self._events: list[LifecycleEvent] = events

    def query(self, sql: str, *, location: str | None) -> Any:
        del sql, location
        assert self._events[-1].event_type == "statement_started"
        return self._job


class _CodedError(RuntimeError):
    def __init__(self, *, attribute_name: str, code: object) -> None:
        super().__init__("driver failure")
        setattr(self, attribute_name, code)


class _SecretCode:
    def __str__(self) -> str:
        return "secret-object-code"


@pytest.mark.parametrize(
    "test_case",
    [
        StatementLifecycleCase(
            description="parameterized batch remains private and correlated",
            sql="INSERT INTO secret VALUES (?)",
            parameters=("private-a", "private-b"),
            expected_event_types=("statement_started", "statement_completed"),
            expected_batch_size=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parameterized_batch_when_driver_executes_then_lifecycle_is_safe_and_once(
    test_case: StatementLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    raw_cursor: _RecordingCursor = _RecordingCursor(events)
    cursor: ObservedCursor = ObservedCursor(raw_cursor=raw_cursor, adapter="postgres")

    with (
        invocation_scope("inv-statement"),
        operation_scope("op-parent"),
        dispatcher_scope(dispatcher),
    ):
        result: Any = cursor.executemany(test_case.sql, test_case.parameters)

    assert result is cursor
    assert raw_cursor.calls == [(test_case.sql, (test_case.parameters,))]
    assert len(raw_cursor.calls) == test_case.expected_call_count
    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert len({event.statement_id for event in events}) == 1
    assert all(event.operation_id == "op-parent" for event in events)
    assert events[0].payload["batch_size"] == test_case.expected_batch_size
    assert events[-1].payload["affected_rows"] == 2
    assert cast(float, events[-1].payload["duration_ms"]) >= 0
    encoded_facts: str = repr(events)
    assert all(parameter not in encoded_facts for parameter in test_case.parameters)
    assert test_case.sql not in encoded_facts
    assert current_execution_identity() is None
    assert current_event_dispatcher() is None


@pytest.mark.parametrize(
    "test_case",
    [
        StatementLifecycleCase(
            description="direct use creates and restores transient context",
            sql="SELECT 1",
            parameters=(),
            expected_event_types=(),
            expected_batch_size=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_context_when_driver_executes_then_result_and_context_are_preserved(
    test_case: StatementLifecycleCase,
) -> None:
    raw_cursor: _DirectCursor = _DirectCursor()
    cursor: ObservedCursor = ObservedCursor(raw_cursor=raw_cursor, adapter="duckdb")

    result: Any = cursor.execute(test_case.sql, test_case.parameters)

    assert result is cursor
    assert raw_cursor.calls == [(test_case.sql, (test_case.parameters,))]
    assert len(raw_cursor.calls) == test_case.expected_call_count
    assert current_execution_identity() is None
    assert current_event_dispatcher() is None


@pytest.mark.parametrize(
    "test_case",
    [
        StatementLifecycleCase(
            description="driver failure remains unchanged when another subscriber fails",
            sql="DELETE FROM private_table",
            parameters=(),
            expected_event_types=("statement_started", "statement_failed"),
            expected_batch_size=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_driver_and_subscriber_when_executing_then_original_error_and_terminal_remain(
    test_case: StatementLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=_FailingSubscriber(), accepts_opaque=False)
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    cursor: ObservedCursor = ObservedCursor(raw_cursor=_FailingCursor(), adapter="sqlserver")

    with (
        invocation_scope("inv-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(LookupError, match="driver failure"),
    ):
        cursor.execute(test_case.sql)

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert len(events) == len(test_case.expected_event_types)
    assert events[-1].payload["error_type"] == "LookupError"
    assert "driver failure" not in repr(events)
    assert test_case.sql not in repr(events)


@pytest.mark.parametrize(
    "test_case",
    [
        StatementLifecycleCase(
            description="BigQuery submission precedes successful result materialization",
            sql="SELECT 1",
            parameters=(),
            expected_event_types=(
                "statement_started",
                "statement_submitted",
                "statement_completed",
            ),
            expected_batch_size=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_job_when_result_succeeds_then_submission_and_terminal_include_job_id(
    test_case: StatementLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    connection: _BigQueryConnection = _BigQueryConnection(
        client=_BigQueryClient(_BigQueryJob(), events), location="EU"
    )

    with invocation_scope("inv-bigquery"), dispatcher_scope(dispatcher):
        connection.execute(test_case.sql)

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[1].payload["job_id"] == "job-current"
    assert events[2].payload["job_id"] == "job-current"


@pytest.mark.parametrize(
    "test_case",
    [
        StatementLifecycleCase(
            description="BigQuery result failure is terminal after submission",
            sql="SELECT private_value",
            parameters=(),
            expected_event_types=(
                "statement_started",
                "statement_submitted",
                "statement_failed",
            ),
            expected_batch_size=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_job_when_result_fails_then_failed_event_follows_submission(
    test_case: StatementLifecycleCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    connection: _BigQueryConnection = _BigQueryConnection(
        client=_BigQueryClient(_FailingBigQueryJob(), events),
        location="EU",
    )

    with (
        invocation_scope("inv-bigquery"),
        dispatcher_scope(dispatcher),
        pytest.raises(RuntimeError, match="private failure"),
    ):
        connection.execute(test_case.sql)

    assert tuple(event.event_type for event in events) == test_case.expected_event_types
    assert events[-1].payload["error_type"] == "RuntimeError"
    assert events[-1].payload["job_id"] == "job-current"
    assert "private failure" not in repr(events)
    assert test_case.sql not in repr(events)


@pytest.mark.parametrize(
    "test_case",
    [
        StatementKindPrivacyCase(
            description="keyword followed by private block comment",
            sql="SELECT/* private-block-comment */ 1",
            expected_statement_kind="SELECT",
            private_fragments=("private-block-comment",),
        ),
        StatementKindPrivacyCase(
            description="private leading line comment",
            sql="-- private-line-comment\nSELECT 1",
            expected_statement_kind="UNKNOWN",
            private_fragments=("private-line-comment",),
        ),
        StatementKindPrivacyCase(
            description="non-keyword-leading private text",
            sql="123 private-non-keyword",
            expected_statement_kind="UNKNOWN",
            private_fragments=("private-non-keyword",),
        ),
        StatementKindPrivacyCase(
            description="empty SQL text",
            sql="",
            expected_statement_kind="UNKNOWN",
            private_fragments=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_text_when_publishing_statement_then_kind_is_safe_and_private_text_is_absent(
    test_case: StatementKindPrivacyCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)

    with (
        invocation_scope("inv-kind-privacy"),
        dispatcher_scope(dispatcher),
        StatementLifecycle(adapter="duckdb", sql=test_case.sql, intent="execute"),
    ):
        pass

    assert events[0].payload["statement_kind"] == test_case.expected_statement_kind
    encoded_events: str = repr(events)
    assert all(fragment not in encoded_events for fragment in test_case.private_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        ErrorCodePrivacyCase(
            description="safe SQLSTATE code",
            attribute_name="sqlstate",
            code="23505",
            expected_error_code="23505",
            private_fragments=(),
        ),
        ErrorCodePrivacyCase(
            description="safe numeric errno",
            attribute_name="errno",
            code=1045,
            expected_error_code="1045",
            private_fragments=(),
        ),
        ErrorCodePrivacyCase(
            description="unsafe secret-bearing code",
            attribute_name="code",
            code="secret customer password",
            expected_error_code=None,
            private_fragments=("secret customer password",),
        ),
        ErrorCodePrivacyCase(
            description="unsafe object code",
            attribute_name="code",
            code=_SecretCode(),
            expected_error_code=None,
            private_fragments=("secret-object-code",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_driver_error_code_when_failing_statement_then_only_safe_identifier_is_published(
    test_case: ErrorCodePrivacyCase,
) -> None:
    events: list[LifecycleEvent] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=events.append, accepts_opaque=False)
    error: _CodedError = _CodedError(attribute_name=test_case.attribute_name, code=test_case.code)

    with (
        invocation_scope("inv-code-privacy"),
        dispatcher_scope(dispatcher),
        StatementLifecycle(adapter="postgres", sql="SELECT 1", intent="execute") as lifecycle,
    ):
        lifecycle.failed(error=error)

    assert events[-1].payload.get("error_code") == test_case.expected_error_code
    encoded_events: str = repr(events)
    assert all(fragment not in encoded_events for fragment in test_case.private_fragments)
