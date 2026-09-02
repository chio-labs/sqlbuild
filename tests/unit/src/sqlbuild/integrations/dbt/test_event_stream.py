from __future__ import annotations

import io
import threading
import time
from collections.abc import Callable, Iterator
from typing import cast

import pytest

from sqlbuild.integrations.dbt._helpers.runtime.event_stream import (
    execute_dbt_json_event_stream,
    parse_dbt_json_event,
    parse_dbt_node_message,
    parse_dbt_node_result,
    parse_dbt_node_start_message,
    parse_dbt_node_start_result,
)
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult, DbtNodeMessage
from sqlbuild.observability import (
    EventDispatcher,
    LifecycleEvent,
    dispatcher_scope,
    invocation_scope,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtEventParseTestCase,
    DbtEventStreamTestCase,
    DbtRuntimeCleanupTestCase,
    DbtSilentStatusRefreshTestCase,
)

_DBT_RESULT_LINE: str = (
    '{"data":{"execution_time":1.0,"index":1,"total":1,"status":"success",'
    '"node_info":{"node_name":"orders","resource_type":"model",'
    '"node_status":"success","unique_id":"model.demo.orders"}},'
    '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n'
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventParseTestCase(
            description="parses dbt model result with node relation metadata",
            event={
                "data": {
                    "description": "sql table model main.base_orders",
                    "execution_time": 0.11,
                    "index": 1,
                    "total": 2,
                    "status": "OK",
                    "node_info": {
                        "materialized": "table",
                        "node_checksum": "abc123",
                        "node_name": "base_orders",
                        "node_relation": {
                            "database": "analytics",
                            "schema": "main",
                            "relation_name": '"analytics"."main"."base_orders"',
                        },
                        "node_status": "success",
                        "resource_type": "model",
                        "unique_id": "model.demo.base_orders",
                    },
                },
                "info": {"level": "info", "name": "LogModelResult", "msg": "OK"},
            },
            expected_unique_id="model.demo.base_orders",
            expected_resource_type="model",
            expected_node_name="base_orders",
            expected_status="OK",
            expected_database="analytics",
            expected_schema="main",
            expected_node_checksum="abc123",
            expected_total=2,
        ),
        DbtEventParseTestCase(
            description="parses dbt test result total from num_models",
            event={
                "data": {
                    "execution_time": 0.03,
                    "index": 3,
                    "num_models": 8,
                    "num_failures": 0,
                    "status": "pass",
                    "node_info": {
                        "node_name": "not_null_stg_orders_order_id",
                        "node_status": "pass",
                        "resource_type": "test",
                        "unique_id": "test.demo.not_null_stg_orders_order_id",
                    },
                },
                "info": {"level": "info", "name": "LogTestResult", "msg": "PASS"},
            },
            expected_unique_id="test.demo.not_null_stg_orders_order_id",
            expected_resource_type="test",
            expected_node_name="not_null_stg_orders_order_id",
            expected_status="pass",
            expected_total=8,
        ),
        DbtEventParseTestCase(
            description="prefers node finished run result status over adapter response",
            event={
                "data": {
                    "execution_time": 0.14,
                    "index": 1,
                    "total": 1,
                    "status": "SELECT 1",
                    "run_result": {"status": "success"},
                    "node_info": {
                        "node_name": "dbt_orders",
                        "resource_type": "model",
                        "unique_id": "model.analytics.dbt_orders",
                    },
                },
                "info": {"level": "info", "name": "NodeFinished", "msg": "SELECT 1"},
            },
            expected_unique_id="model.analytics.dbt_orders",
            expected_resource_type="model",
            expected_node_name="dbt_orders",
            expected_status="success",
            expected_total=1,
        ),
        DbtEventParseTestCase(
            description="uses node status when result event status is adapter response",
            event={
                "data": {
                    "execution_time": 0.14,
                    "index": 1,
                    "total": 1,
                    "status": "SELECT 1",
                    "node_info": {
                        "node_name": "dbt_orders",
                        "node_status": "success",
                        "resource_type": "model",
                        "unique_id": "model.analytics.dbt_orders",
                    },
                },
                "info": {"level": "info", "name": "LogModelResult", "msg": "SELECT 1"},
            },
            expected_unique_id="model.analytics.dbt_orders",
            expected_resource_type="model",
            expected_node_name="dbt_orders",
            expected_status="success",
            expected_total=1,
        ),
        DbtEventParseTestCase(
            description="parses dbt unit test result",
            event={
                "data": {
                    "execution_time": 0.07,
                    "index": 1,
                    "total": 1,
                    "run_result": {"status": "pass"},
                    "node_info": {
                        "node_name": "stg_orders_unit",
                        "resource_type": "unit_test",
                        "unique_id": "unit_test.analytics.stg_orders_unit",
                    },
                },
                "info": {"level": "info", "name": "NodeFinished", "msg": "PASS"},
            },
            expected_unique_id="unit_test.analytics.stg_orders_unit",
            expected_resource_type="unit_test",
            expected_node_name="stg_orders_unit",
            expected_status="pass",
            expected_total=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_result_event_when_parsing_then_returns_node_execution_result(
    test_case: DbtEventParseTestCase,
) -> None:
    result: DbtNodeExecutionResult | None = parse_dbt_node_result(
        event=test_case.event,
        messages_by_unique_id=None,
    )

    assert result is not None
    assert result.unique_id == test_case.expected_unique_id
    assert result.resource_type == test_case.expected_resource_type
    assert result.node_name == test_case.expected_node_name
    assert result.status == test_case.expected_status
    assert result.database == test_case.expected_database
    assert result.schema == test_case.expected_schema
    assert result.node_checksum == test_case.expected_node_checksum
    assert result.total == test_case.expected_total


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventParseTestCase(
            description="attaches buffered error message to node result",
            event={
                "data": {
                    "execution_time": 0.44,
                    "index": 2,
                    "total": 2,
                    "status": "error",
                    "node_info": {
                        "node_name": "fact_orders",
                        "node_status": "error",
                        "resource_type": "model",
                        "unique_id": "model.demo.fact_orders",
                    },
                },
                "info": {"level": "error", "name": "LogModelResult", "msg": "ERROR"},
            },
            expected_unique_id="model.demo.fact_orders",
            expected_resource_type="model",
            expected_node_name="fact_orders",
            expected_status="error",
            expected_message_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_buffered_node_message_when_parsing_result_then_attaches_message(
    test_case: DbtEventParseTestCase,
) -> None:
    messages_by_unique_id: dict[str, list[DbtNodeMessage]] = {
        test_case.expected_unique_id: [
            DbtNodeMessage(level="error", message="relation raw.orders does not exist")
        ]
    }

    result: DbtNodeExecutionResult | None = parse_dbt_node_result(
        event=test_case.event,
        messages_by_unique_id=messages_by_unique_id,
    )

    assert result is not None
    assert len(result.messages) == test_case.expected_message_count
    assert result.messages[0].message == "relation raw.orders does not exist"
    assert messages_by_unique_id == {}


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventParseTestCase(
            description="parses node-scoped run result error message",
            event={
                "data": {
                    "msg": "Database Error in model fact_orders",
                    "node_info": {
                        "node_name": "fact_orders",
                        "resource_type": "model",
                        "unique_id": "model.demo.fact_orders",
                    },
                },
                "info": {
                    "level": "error",
                    "name": "RunResultError",
                    "msg": "Database Error in model fact_orders",
                },
            },
            expected_unique_id="model.demo.fact_orders",
            expected_resource_type="model",
            expected_node_name="fact_orders",
            expected_status="error",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_scoped_error_event_when_parsing_then_returns_node_message(
    test_case: DbtEventParseTestCase,
) -> None:
    message: DbtNodeMessage | None = parse_dbt_node_message(event=test_case.event)

    assert message is not None
    assert message.level == test_case.expected_status
    assert "Database Error" in message.message


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventParseTestCase(
            description="ignores non-json and invocation-level json lines",
            event={
                "data": {"stat_line": "1 model"},
                "info": {"level": "info", "name": "FoundStats", "msg": "Found 1 model"},
            },
            expected_unique_id="",
            expected_resource_type="",
            expected_node_name="",
            expected_status="",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_non_result_event_when_parsing_then_returns_none(
    test_case: DbtEventParseTestCase,
) -> None:
    non_json_event: dict[str, object] | None = parse_dbt_json_event(line="not json")
    result: DbtNodeExecutionResult | None = parse_dbt_node_result(
        event=test_case.event,
        messages_by_unique_id=None,
    )

    assert non_json_event is None
    assert result is None
    assert test_case.expected_unique_id == ""
    assert test_case.expected_status == ""


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventStreamTestCase(
            description="streams node results to callback",
            stdout_lines=(
                '{"data":{"execution_time":0.1,"index":1,"total":1,"status":"OK",'
                '"node_info":{"node_name":"base_orders","resource_type":"model",'
                '"unique_id":"model.demo.base_orders"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
            ),
            expected_unique_ids=("model.demo.base_orders",),
        ),
        DbtEventStreamTestCase(
            description="dedupes fusion LogModelResult and NodeFinished for one node",
            stdout_lines=(
                '{"data":{"execution_time":0.1,"index":1,"total":1,"status":"success",'
                '"node_info":{"node_name":"dbt_orders","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.dbt_orders"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
                '{"data":{"execution_time":0.1,"index":1,"total":1,"status":"SELECT 1",'
                '"run_result":{"status":"success"},'
                '"node_info":{"node_name":"dbt_orders","resource_type":"model",'
                '"unique_id":"model.analytics.dbt_orders"}},'
                '"info":{"level":"info","name":"NodeFinished","msg":"SELECT 1"}}\n',
            ),
            expected_unique_ids=("model.analytics.dbt_orders",),
        ),
        DbtEventStreamTestCase(
            description="records distinct nodes once each across mixed result events",
            stdout_lines=(
                '{"data":{"execution_time":0.1,"index":1,"total":2,"status":"success",'
                '"node_info":{"node_name":"stg_orders","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.stg_orders"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
                '{"data":{"execution_time":0.2,"index":2,"total":2,"status":"success",'
                '"run_result":{"status":"success"},'
                '"node_info":{"node_name":"fact_orders","resource_type":"model",'
                '"unique_id":"model.analytics.fact_orders"}},'
                '"info":{"level":"info","name":"NodeFinished","msg":"OK"}}\n',
            ),
            expected_unique_ids=(
                "model.analytics.stg_orders",
                "model.analytics.fact_orders",
            ),
        ),
        DbtEventStreamTestCase(
            description="renders node started progress before final result",
            stdout_lines=(
                '{"data":{"node_info":{"node_name":"bias__stg_hkjc",'
                '"resource_type":"model","unique_id":"model.analytics.bias__stg_hkjc"}},'
                '"info":{"level":"info","name":"NodeStarted","msg":"START"}}\n',
                '{"data":{"execution_time":20.4,"index":1,"total":1,"status":"success",'
                '"node_info":{"node_name":"bias__stg_hkjc","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.bias__stg_hkjc"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
            ),
            expected_unique_ids=("model.analytics.bias__stg_hkjc",),
            expected_output_fragments=(
                "Running dbt model bias__stg_hkjc...",
                "model     bias__stg_hkjc                 START",
                "model     bias__stg_hkjc                 OK     20.40s",
            ),
            expected_rendered_rows=2,
        ),
        DbtEventStreamTestCase(
            description="renders log start line progress before final result",
            stdout_lines=(
                '{"data":{"node_info":{"node_name":"bias__stg_hkjc",'
                '"resource_type":"model","unique_id":"model.analytics.bias__stg_hkjc"}},'
                '"info":{"level":"info","name":"LogStartLine","msg":"START"}}\n',
                '{"data":{"execution_time":20.4,"index":1,"total":1,"status":"success",'
                '"node_info":{"node_name":"bias__stg_hkjc","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.bias__stg_hkjc"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
            ),
            expected_unique_ids=("model.analytics.bias__stg_hkjc",),
            expected_output_fragments=(
                "Running dbt model bias__stg_hkjc...",
                "model     bias__stg_hkjc                 START",
                "model     bias__stg_hkjc                 OK     20.40s",
            ),
            expected_rendered_rows=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_json_stream_when_running_then_invokes_node_result_callback(
    test_case: DbtEventStreamTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_events: list[LifecycleEvent] = []

    class StubProcess:
        stdout: io.StringIO = io.StringIO("".join(test_case.stdout_lines))

        def wait(self) -> int:
            assert tuple(event.event_type for event in lifecycle_events) == ("operation_started",)
            return 0

    captured_results: list[DbtNodeExecutionResult] = []

    def launch(*args: object, **kwargs: object) -> StubProcess:
        del args, kwargs
        assert lifecycle_events[-1].event_type == "operation_started"
        return StubProcess()

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen", launch
    )

    stream: io.StringIO = io.StringIO()
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=lifecycle_events.append, accepts_opaque=False)
    returncode: int
    with invocation_scope("inv-dbt-stream"), dispatcher_scope(dispatcher):
        returncode, results = execute_dbt_json_event_stream(
            argv=("dbt", "run"),
            cwd=None,
            stream=stream,
            use_color=False,
            target_path=None,
            on_node_result=captured_results.append,
        )

    assert returncode == 0
    assert tuple(result.unique_id for result in results) == test_case.expected_unique_ids
    assert tuple(result.unique_id for result in captured_results) == test_case.expected_unique_ids
    assert tuple(event.event_type for event in lifecycle_events) == (
        "operation_started",
        "operation_completed",
    )
    assert "".join(test_case.stdout_lines) not in repr(lifecycle_events)
    output: str = stream.getvalue()
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    rendered_rows: int = output.count("   model")
    expected_rendered_rows: int = test_case.expected_rendered_rows or len(
        test_case.expected_unique_ids
    )
    assert rendered_rows == expected_rendered_rows


@pytest.mark.parametrize(
    "test_case",
    (
        DbtRuntimeCleanupTestCase(
            description="callback failure cleans launched dbt runtime before terminal",
            expected_error="original callback failure",
            expected_actions=(
                "operation_started",
                "popen",
                "status_start",
                "thread_start",
                "status_close",
                "thread_join",
                "poll",
                "terminate",
                "wait",
                "operation_failed",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_callback_failure_when_streaming_then_runtime_cleans_before_failed_terminal(
    test_case: DbtRuntimeCleanupTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[str] = []
    lifecycle_events: list[LifecycleEvent] = []

    class TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    class StatusReporter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def start(self, message: str) -> None:
            del message
            actions.append("status_start")

        def close(self) -> None:
            assert lifecycle_events[-1].event_type == "operation_started"
            actions.append("status_close")

    class StatusThread:
        def __init__(self, status_stop: threading.Event) -> None:
            self._status_stop: threading.Event = status_stop

        def join(self, timeout: float) -> None:
            del timeout
            assert lifecycle_events[-1].event_type == "operation_started"
            assert self._status_stop.is_set()
            actions.append("thread_join")

    class Process:
        stdout: io.StringIO = io.StringIO(_DBT_RESULT_LINE)

        def poll(self) -> None:
            actions.append("poll")
            return None

        def terminate(self) -> None:
            assert lifecycle_events[-1].event_type == "operation_started"
            actions.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            assert timeout == 1
            assert lifecycle_events[-1].event_type == "operation_started"
            actions.append("wait")
            return -15

    def launch(*args: object, **kwargs: object) -> Process:
        del args, kwargs
        actions.append("popen")
        return Process()

    def start_thread(*args: object, **kwargs: object) -> StatusThread:
        del args
        actions.append("thread_start")
        return StatusThread(cast(threading.Event, kwargs["status_stop"]))

    def record_event(event: LifecycleEvent) -> None:
        lifecycle_events.append(event)
        actions.append(event.event_type)

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen", launch
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.TransientStatusReporter",
        StatusReporter,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream._start_active_node_status_refresher",
        start_thread,
    )
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=record_event, accepts_opaque=False)

    with (
        invocation_scope("inv-dbt-callback-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(RuntimeError, match=test_case.expected_error),
    ):
        _ = execute_dbt_json_event_stream(
            argv=("dbt", "run"),
            cwd=None,
            stream=TtyStream(),
            use_color=False,
            target_path=None,
            on_node_result=lambda result: (_ for _ in ()).throw(
                RuntimeError(test_case.expected_error)
            ),
        )

    assert tuple(actions) == test_case.expected_actions


@pytest.mark.parametrize(
    "test_case",
    (
        DbtRuntimeCleanupTestCase(
            description="process wait failure reaps child before terminal",
            expected_error="original wait failure",
            expected_actions=(
                "operation_started",
                "main_wait",
                "poll",
                "terminate",
                "cleanup_wait",
                "operation_failed",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_process_wait_failure_when_streaming_then_child_cleanup_precedes_terminal(
    test_case: DbtRuntimeCleanupTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[str] = []
    lifecycle_events: list[LifecycleEvent] = []
    wait_labels: Iterator[str] = iter(("main_wait", "cleanup_wait"))
    wait_outcomes: Iterator[Callable[[], int]] = iter(
        (
            lambda: (_ for _ in ()).throw(RuntimeError(test_case.expected_error)),
            lambda: -15,
        )
    )

    class Process:
        stdout: io.StringIO = io.StringIO()

        def poll(self) -> None:
            actions.append("poll")
            return None

        def terminate(self) -> None:
            assert lifecycle_events[-1].event_type == "operation_started"
            actions.append("terminate")

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            assert lifecycle_events[-1].event_type == "operation_started"
            actions.append(next(wait_labels))
            return next(wait_outcomes)()

    def record_event(event: LifecycleEvent) -> None:
        lifecycle_events.append(event)
        actions.append(event.event_type)

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: Process(),
    )
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=record_event, accepts_opaque=False)

    with (
        invocation_scope("inv-dbt-wait-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(RuntimeError, match=test_case.expected_error),
    ):
        _ = execute_dbt_json_event_stream(
            argv=("dbt", "run"),
            cwd=None,
            stream=io.StringIO(),
            use_color=False,
            target_path=None,
            enable_status=False,
        )

    assert tuple(actions) == test_case.expected_actions


@pytest.mark.parametrize(
    "test_case",
    (
        DbtRuntimeCleanupTestCase(
            description="popen failure starts no status thread",
            expected_error="failed to execute dbt",
            expected_actions=("operation_started", "popen", "operation_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_popen_failure_when_streaming_then_no_status_runtime_is_started(
    test_case: DbtRuntimeCleanupTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[str] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(
        subscriber=lambda event: actions.append(event.event_type), accepts_opaque=False
    )

    def launch(*args: object, **kwargs: object) -> None:
        del args, kwargs
        actions.append("popen")
        raise OSError("private launch failure")

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen", launch
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream._start_active_node_status_refresher",
        lambda *args, **kwargs: actions.append("unexpected_thread"),
    )

    with (
        invocation_scope("inv-dbt-popen-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(Exception, match=test_case.expected_error),
    ):
        _ = execute_dbt_json_event_stream(
            argv=("dbt", "run"),
            cwd=None,
            stream=io.StringIO(),
            use_color=False,
            target_path=None,
        )

    assert tuple(actions) == test_case.expected_actions


@pytest.mark.parametrize(
    "test_case",
    (
        DbtRuntimeCleanupTestCase(
            description="interrupted dbt wait leaves operation unmatched",
            expected_error="",
            expected_actions=("operation_started",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unobserved_dbt_interruption_when_cleanup_reaps_then_no_terminal_is_fabricated(
    test_case: DbtRuntimeCleanupTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle_events: list[LifecycleEvent] = []
    wait_outcomes: Iterator[Callable[[], int]] = iter(
        (
            lambda: (_ for _ in ()).throw(KeyboardInterrupt),
            lambda: -2,
        )
    )

    class Process:
        stdout: io.StringIO = io.StringIO()

        def poll(self) -> int:
            return -2

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            return next(wait_outcomes)()

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: Process(),
    )
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=lifecycle_events.append, accepts_opaque=False)

    with (
        invocation_scope("inv-dbt-interrupted"),
        dispatcher_scope(dispatcher),
        pytest.raises(KeyboardInterrupt),
    ):
        _ = execute_dbt_json_event_stream(
            argv=("dbt", "run"),
            cwd=None,
            stream=io.StringIO(),
            use_color=False,
            target_path=None,
            enable_status=False,
        )

    assert tuple(event.event_type for event in lifecycle_events) == test_case.expected_actions


@pytest.mark.parametrize(
    "test_case",
    (
        DbtRuntimeCleanupTestCase(
            description="cleanup failures preserve parse exception",
            expected_error="original parse failure",
            expected_actions=(
                "operation_started",
                "thread_join",
                "status_close",
                "poll",
                "terminate",
                "wait",
                "kill",
                "wait",
                "operation_failed",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_cleanup_failures_when_parse_raises_then_original_exception_is_preserved(
    test_case: DbtRuntimeCleanupTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions: list[str] = []

    class TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    class FailingStatus:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def start(self, message: str) -> None:
            del message

        def close(self) -> None:
            actions.append("status_close")
            raise RuntimeError("cleanup status failure")

    class FailingThread:
        def join(self, timeout: float) -> None:
            del timeout
            actions.append("thread_join")
            raise RuntimeError("cleanup thread failure")

    class FailingProcess:
        stdout: io.StringIO = io.StringIO(_DBT_RESULT_LINE)

        def poll(self) -> None:
            actions.append("poll")
            raise RuntimeError("cleanup poll failure")

        def terminate(self) -> None:
            actions.append("terminate")
            raise RuntimeError("cleanup terminate failure")

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            actions.append("wait")
            raise RuntimeError("cleanup wait failure")

        def kill(self) -> None:
            actions.append("kill")
            raise RuntimeError("cleanup kill failure")

    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(
        subscriber=lambda event: actions.append(event.event_type), accepts_opaque=False
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: FailingProcess(),
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.TransientStatusReporter",
        FailingStatus,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream._start_active_node_status_refresher",
        lambda *args, **kwargs: FailingThread(),
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.parse_dbt_json_event",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError(test_case.expected_error)),
    )

    with (
        invocation_scope("inv-dbt-cleanup-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(RuntimeError, match=test_case.expected_error),
    ):
        _ = execute_dbt_json_event_stream(
            argv=("dbt", "run"),
            cwd=None,
            stream=TtyStream(),
            use_color=False,
            target_path=None,
        )

    assert tuple(actions) == test_case.expected_actions


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSilentStatusRefreshTestCase(
            description="active node elapsed refreshes without dbt events",
            silent_seconds=1.15,
            refresh_seconds=0.05,
            expected_initial_status="running 1 dbt node: slow_model <1s",
            expected_refreshed_status="running 1 dbt node: slow_model 1s",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_dbt_node_when_dbt_stream_is_silent_then_status_elapsed_updates(
    test_case: DbtSilentStatusRefreshTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status_messages: list[str] = []

    class CapturingStatusReporter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def start(self, message: str) -> None:
            status_messages.append(message)

        def update(self, message: str) -> None:
            status_messages.append(message)

        def close(self) -> None:
            pass

    class TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    class DelayedStdout:
        def __enter__(self) -> DelayedStdout:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def __iter__(self) -> object:
            yield (
                '{"data":{"index":1,"total":1,"node_info":{"node_name":"slow_model",'
                '"resource_type":"model","unique_id":"model.analytics.slow_model"}},'
                '"info":{"level":"info","name":"LogStartLine","msg":"START"}}\n'
            )
            time.sleep(test_case.silent_seconds)
            yield (
                '{"data":{"execution_time":1.2,"index":1,"total":1,"status":"success",'
                '"node_info":{"node_name":"slow_model","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.slow_model"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n'
            )

    class StubProcess:
        stdout: DelayedStdout = DelayedStdout()

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.TransientStatusReporter",
        CapturingStatusReporter,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream._DBT_STATUS_REFRESH_SECONDS",
        test_case.refresh_seconds,
    )
    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: StubProcess(),
    )

    returncode: int
    returncode, _ = execute_dbt_json_event_stream(
        argv=("dbt", "run"),
        cwd=None,
        stream=TtyStream(),
        use_color=False,
        target_path=None,
    )

    assert returncode == 0
    assert test_case.expected_initial_status in status_messages
    assert test_case.expected_refreshed_status in status_messages


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventParseTestCase(
            description="parses node started event into progress message",
            event={
                "data": {
                    "node_info": {
                        "node_name": "base_orders",
                        "resource_type": "model",
                        "unique_id": "model.demo.base_orders",
                    }
                },
                "info": {"level": "info", "name": "NodeStarted", "msg": "START"},
            },
            expected_unique_id="model.demo.base_orders",
            expected_resource_type="model",
            expected_node_name="base_orders",
            expected_status="Running dbt model base_orders...",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_started_event_when_parsing_then_returns_progress_message(
    test_case: DbtEventParseTestCase,
) -> None:
    message: str | None = parse_dbt_node_start_message(event=test_case.event)

    assert message == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    [
        DbtEventParseTestCase(
            description="parses node started event into start result",
            event={
                "data": {
                    "index": 3,
                    "total": 7,
                    "node_info": {
                        "node_name": "base_orders",
                        "resource_type": "model",
                        "unique_id": "model.demo.base_orders",
                    },
                },
                "info": {"level": "info", "name": "NodeStarted", "msg": "START"},
            },
            expected_unique_id="model.demo.base_orders",
            expected_resource_type="model",
            expected_node_name="base_orders",
            expected_status="start",
            expected_total=7,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_started_event_when_parsing_then_returns_start_result(
    test_case: DbtEventParseTestCase,
) -> None:
    result: DbtNodeExecutionResult | None = parse_dbt_node_start_result(event=test_case.event)

    assert result is not None
    assert result.unique_id == test_case.expected_unique_id
    assert result.resource_type == test_case.expected_resource_type
    assert result.node_name == test_case.expected_node_name
    assert result.status == test_case.expected_status
    assert result.total == test_case.expected_total
