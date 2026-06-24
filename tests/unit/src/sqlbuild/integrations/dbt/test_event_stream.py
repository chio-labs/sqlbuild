from __future__ import annotations

import io

import pytest

from sqlbuild.integrations.dbt.helpers.runtime.event_stream import (
    execute_dbt_json_event_stream,
    parse_dbt_json_event,
    parse_dbt_node_message,
    parse_dbt_node_result,
    parse_dbt_node_start_message,
)
from sqlbuild.integrations.dbt.models import DbtNodeExecutionResult, DbtNodeMessage
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtEventParseTestCase,
    DbtEventStreamTestCase,
)

DBT_RESULT_PARSE_TEST_CASES: list[DbtEventParseTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    DBT_RESULT_PARSE_TEST_CASES,
    ids=[case.description for case in DBT_RESULT_PARSE_TEST_CASES],
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
    ids=["attaches buffered error message to node result"],
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
    ids=["parses node-scoped run result error message"],
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
    ids=["ignores non-json and invocation-level json lines"],
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


DBT_EVENT_STREAM_TEST_CASES: list[DbtEventStreamTestCase] = [
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
        expected_output_fragments=("Running dbt model bias__stg_hkjc...",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DBT_EVENT_STREAM_TEST_CASES,
    ids=[case.description for case in DBT_EVENT_STREAM_TEST_CASES],
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
        "sqlbuild.integrations.dbt.helpers.runtime.event_stream.subprocess.Popen",
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
    assert rendered_rows == len(test_case.expected_unique_ids)


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
    ids=["parses node started event into progress message"],
)
def test_given_node_started_event_when_parsing_then_returns_progress_message(
    test_case: DbtEventParseTestCase,
) -> None:
    message: str | None = parse_dbt_node_start_message(event=test_case.event)

    assert message == test_case.expected_status
