from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from sqlbuild._native import (
    DbtEventStream,
    DbtEventStreamUpdate,
    DbtInteropRuntimeError,
    DbtNodeExecutionResult,
    execute_dbt_json_event_stream,
)
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
from tests.unit.src.sqlbuild.integrations.dbt.helpers import consume_dbt_events, fake_dbt_argv

_STOPPED_WITHIN_SECONDS: float = 30.0
_DBT_SLOW_START_LINE: str = (
    '{"data":{"index":1,"total":1,"node_info":{"node_name":"slow_model",'
    '"resource_type":"model","unique_id":"model.analytics.slow_model"}},'
    '"info":{"level":"info","name":"LogStartLine","msg":"START"}}\n'
)
_DBT_SLOW_RESULT_LINE: str = (
    '{"data":{"execution_time":1.2,"index":1,"total":1,"status":"success",'
    '"node_info":{"node_name":"slow_model","resource_type":"model",'
    '"node_status":"success","unique_id":"model.analytics.slow_model"}},'
    '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n'
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
    update: DbtEventStreamUpdate | None = consume_dbt_events(test_case.event)

    assert update is not None
    result: DbtNodeExecutionResult | None = update.result
    assert result is not None
    assert update.finished is True
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
                "info": {"level": "info", "name": "LogModelResult", "msg": "ERROR"},
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
    message_event: dict[str, object] = {
        "data": {
            "msg": " relation raw.orders does not exist\n",
            "node_info": {"unique_id": test_case.expected_unique_id},
        },
        "info": {"level": "error", "name": "RunResultError"},
    }
    stream: DbtEventStream = DbtEventStream(
        display_total=None, detail_by_unique_id=None, use_color=False
    )

    message_update: DbtEventStreamUpdate | None = stream.consume(json.dumps(message_event))
    update: DbtEventStreamUpdate | None = stream.consume(json.dumps(test_case.event))
    repeated: DbtEventStreamUpdate | None = stream.consume(json.dumps(test_case.event))

    assert message_update is None
    assert repeated is None
    assert update is not None
    result: DbtNodeExecutionResult | None = update.result
    assert result is not None
    assert len(result.messages) == test_case.expected_message_count
    assert result.messages[0].message == "relation raw.orders does not exist"
    assert update.row is not None
    assert "error     relation raw.orders does not exist" in update.row


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
def test_given_node_scoped_error_event_when_parsing_then_attaches_node_message(
    test_case: DbtEventParseTestCase,
) -> None:
    result_event: dict[str, object] = {
        "data": {"status": "error", "node_info": {"unique_id": test_case.expected_unique_id}},
        "info": {"level": "info", "name": "LogModelResult"},
    }

    update: DbtEventStreamUpdate | None = consume_dbt_events(test_case.event, result_event)

    assert update is not None
    result: DbtNodeExecutionResult | None = update.result
    assert result is not None
    assert result.messages[0].level == test_case.expected_status
    assert "Database Error" in result.messages[0].message


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
    stream: DbtEventStream = DbtEventStream(
        display_total=None, detail_by_unique_id=None, use_color=False
    )

    assert stream.consume("not json") is None
    assert consume_dbt_events(test_case.event) is None
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
                '{"data":{"node_info":{"node_name":"bias__stg_partner_feed",'
                '"resource_type":"model","unique_id":"model.analytics.bias__stg_partner_feed"}},'
                '"info":{"level":"info","name":"NodeStarted","msg":"START"}}\n',
                '{"data":{"execution_time":20.4,"index":1,"total":1,"status":"success",'
                '"node_info":{"node_name":"bias__stg_partner_feed","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.bias__stg_partner_feed"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
            ),
            expected_unique_ids=("model.analytics.bias__stg_partner_feed",),
            expected_output_fragments=(
                "Running dbt model bias__stg_partner_feed...",
                "model     bias__stg_partner_feed         START",
                "model     bias__stg_partner_feed         OK     20.40s",
            ),
            expected_rendered_rows=2,
        ),
        DbtEventStreamTestCase(
            description="renders log start line progress before final result",
            stdout_lines=(
                '{"data":{"node_info":{"node_name":"bias__stg_partner_feed",'
                '"resource_type":"model","unique_id":"model.analytics.bias__stg_partner_feed"}},'
                '"info":{"level":"info","name":"LogStartLine","msg":"START"}}\n',
                '{"data":{"execution_time":20.4,"index":1,"total":1,"status":"success",'
                '"node_info":{"node_name":"bias__stg_partner_feed","resource_type":"model",'
                '"node_status":"success","unique_id":"model.analytics.bias__stg_partner_feed"}},'
                '"info":{"level":"info","name":"LogModelResult","msg":"OK"}}\n',
            ),
            expected_unique_ids=("model.analytics.bias__stg_partner_feed",),
            expected_output_fragments=(
                "Running dbt model bias__stg_partner_feed...",
                "model     bias__stg_partner_feed         START",
                "model     bias__stg_partner_feed         OK     20.40s",
            ),
            expected_rendered_rows=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_json_stream_when_running_then_invokes_node_result_callback(
    test_case: DbtEventStreamTestCase,
    tmp_path: Path,
) -> None:
    lifecycle_events: list[LifecycleEvent] = []
    captured_results: list[DbtNodeExecutionResult] = []
    stream: io.StringIO = io.StringIO()
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(subscriber=lifecycle_events.append, accepts_opaque=False)

    with invocation_scope("inv-dbt-stream"), dispatcher_scope(dispatcher):
        returncode, results = execute_dbt_json_event_stream(
            argv=fake_dbt_argv(tmp_path, lines=test_case.stdout_lines),
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
            description="callback failure stops dbt before the failed terminal",
            expected_error="original callback failure",
            expected_actions=("operation_started", "operation_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_callback_failure_when_streaming_then_runtime_cleans_before_failed_terminal(
    test_case: DbtRuntimeCleanupTestCase,
    tmp_path: Path,
) -> None:
    actions: list[str] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(
        subscriber=lambda event: actions.append(event.event_type), accepts_opaque=False
    )
    started: float = time.monotonic()

    with (
        invocation_scope("inv-dbt-callback-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(RuntimeError, match=test_case.expected_error),
    ):
        _ = execute_dbt_json_event_stream(
            argv=fake_dbt_argv(tmp_path, lines=(_DBT_RESULT_LINE,), sleep_seconds=60),
            cwd=None,
            stream=io.StringIO(),
            use_color=False,
            target_path=None,
            on_node_result=lambda result: (_ for _ in ()).throw(
                RuntimeError(test_case.expected_error)
            ),
        )

    assert tuple(actions) == test_case.expected_actions
    assert time.monotonic() - started < _STOPPED_WITHIN_SECONDS


@pytest.mark.parametrize(
    "test_case",
    (
        DbtRuntimeCleanupTestCase(
            description="launch failure starts no status and fails the operation",
            expected_error="failed to execute dbt",
            expected_actions=("operation_started", "operation_failed"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_popen_failure_when_streaming_then_no_status_runtime_is_started(
    test_case: DbtRuntimeCleanupTestCase,
    tmp_path: Path,
) -> None:
    actions: list[str] = []
    dispatcher: EventDispatcher = EventDispatcher()
    dispatcher.subscribe_lifecycle(
        subscriber=lambda event: actions.append(event.event_type), accepts_opaque=False
    )
    stream: io.StringIO = io.StringIO()

    with (
        invocation_scope("inv-dbt-popen-failure"),
        dispatcher_scope(dispatcher),
        pytest.raises(DbtInteropRuntimeError, match=test_case.expected_error) as raised,
    ):
        _ = execute_dbt_json_event_stream(
            argv=(str(tmp_path / "missing-dbt"), "run"),
            cwd=None,
            stream=stream,
            use_color=False,
            target_path=None,
        )

    assert tuple(actions) == test_case.expected_actions
    assert isinstance(raised.value.__cause__, FileNotFoundError)
    assert stream.getvalue() == ""


@pytest.mark.parametrize(
    "test_case",
    [
        DbtSilentStatusRefreshTestCase(
            description="active node elapsed refreshes without dbt events",
            silent_seconds=2.4,
            refresh_seconds=1.0,
            expected_initial_status="running 1 dbt node: slow_model <1s",
            expected_refreshed_status="running 1 dbt node: slow_model 1s",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_active_dbt_node_when_dbt_stream_is_silent_then_status_elapsed_updates(
    test_case: DbtSilentStatusRefreshTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TtyStream(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setenv("SQLBUILD_NO_PROGRESS", "1")
    stream: TtyStream = TtyStream()

    returncode, _ = execute_dbt_json_event_stream(
        argv=fake_dbt_argv(
            tmp_path,
            lines=(_DBT_SLOW_START_LINE,),
            sleep_seconds=test_case.silent_seconds,
            after_lines=(_DBT_SLOW_RESULT_LINE,),
        ),
        cwd=None,
        stream=stream,
        use_color=False,
        target_path=None,
    )
    status_lines: list[str] = stream.getvalue().splitlines()

    assert returncode == 0
    assert test_case.refresh_seconds < test_case.silent_seconds
    assert test_case.expected_initial_status in status_lines
    assert test_case.expected_refreshed_status in status_lines


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
    update: DbtEventStreamUpdate | None = consume_dbt_events(test_case.event)

    assert update is not None
    assert update.status_message == test_case.expected_status


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
    update: DbtEventStreamUpdate | None = consume_dbt_events(test_case.event)

    assert update is not None
    result: DbtNodeExecutionResult | None = update.result
    assert result is not None
    assert update.finished is False
    assert result.unique_id == test_case.expected_unique_id
    assert result.resource_type == test_case.expected_resource_type
    assert result.node_name == test_case.expected_node_name
    assert result.status == test_case.expected_status
    assert result.total == test_case.expected_total
