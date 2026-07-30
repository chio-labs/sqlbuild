from __future__ import annotations

import io
import time

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
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtEventParseTestCase,
    DbtEventStreamTestCase,
    DbtSilentStatusRefreshTestCase,
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
    class StubProcess:
        stdout: io.StringIO = io.StringIO("".join(test_case.stdout_lines))

        def wait(self) -> int:
            return 0

    captured_results: list[DbtNodeExecutionResult] = []

    monkeypatch.setattr(
        "sqlbuild.integrations.dbt._helpers.runtime.event_stream.subprocess.Popen",
        lambda *args, **kwargs: StubProcess(),
    )

    stream: io.StringIO = io.StringIO()
    returncode: int
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
