"""Tests for Python task and asset runtime contexts."""

from __future__ import annotations

import inspect
import logging

import pytest

from sqlbuild.adapter.shared.models import LifeCycleEvent, StatementRecorder
from sqlbuild.assets import AssetContext
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.python_nodes.models import PythonNodeResult, PythonNodeSkipResult
from sqlbuild.tasks import TaskContext
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonNodeContextHelperTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    PythonNodeContextTestAdapter,
    assert_base_context_fields,
    build_asset_context,
    build_task_context,
    loader_only_attribute_names,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeContextHelperTestCase(
            description="task context records helper calls and qualifies names",
            raw_name="scratch_orders",
            database="override_db",
            schema="override_schema",
            expected_qualified_name="override_db.override_schema.scratch_orders",
            expected_execute_result="result:CREATE TABLE scratch_orders AS SELECT 1",
            expected_query_result="result:SELECT * FROM scratch_orders",
            expected_recorded_events=(
                "CREATE TABLE scratch_orders AS SELECT 1",
                "SELECT * FROM scratch_orders",
                "loading scratch orders",
            ),
            expected_logger_name="sqlbuild.task.fetch_orders",
            expected_run_id="test_run",
            expected_environment="dev",
            expected_vars={"batch": "hourly"},
        )
    ],
    ids=["task context records helper calls and qualifies names"],
)
def test_given_task_context_when_using_helpers_then_records_and_qualifies_names(
    test_case: PythonNodeContextHelperTestCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter: PythonNodeContextTestAdapter = PythonNodeContextTestAdapter()
    statement_recorder: StatementRecorder = StatementRecorder()
    context: TaskContext = build_task_context(
        adapter=adapter,
        statement_recorder=statement_recorder,
        logger_name=test_case.expected_logger_name,
    )

    with caplog.at_level(logging.INFO, logger=test_case.expected_logger_name):
        execute_result: object = context.execute_sql("CREATE TABLE scratch_orders AS SELECT 1")
        query_result: object = context.query("SELECT * FROM scratch_orders")
        context.log("loading scratch orders")
    qualified_name: str = context.qualify_name(
        test_case.raw_name,
        database=test_case.database,
        schema=test_case.schema,
    )
    default_qualified_name: str = context.qualify_name(test_case.raw_name)
    already_qualified_name: str = context.qualify_name("custom.schema.table")

    assert execute_result == test_case.expected_execute_result
    assert query_result == test_case.expected_query_result
    assert qualified_name == test_case.expected_qualified_name
    assert default_qualified_name == "default_db.default_schema.scratch_orders"
    assert already_qualified_name == "custom.schema.table"
    assert context.logger.name == test_case.expected_logger_name
    assert context.run_id == test_case.expected_run_id
    assert context.environment == test_case.expected_environment
    assert context.vars == test_case.expected_vars
    assert "loading scratch orders" in caplog.messages
    events: tuple[LifeCycleEvent, ...] = statement_recorder.snapshot()
    assert tuple(event.content for event in events) == test_case.expected_recorded_events
    assert_base_context_fields(context)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeContextHelperTestCase(
            description="asset context returns asset result and skip signal",
            raw_name="published_customers",
            database=None,
            schema=None,
            expected_qualified_name="default_db.default_schema.published_customers",
            expected_execute_result="s3://exports/customers.parquet",
            expected_query_result="No new source rows",
            expected_recorded_events=(),
            expected_logger_name="sqlbuild.asset.export_customers",
            expected_run_id="test_run",
            expected_environment="dev",
            expected_vars={"batch": "hourly"},
        )
    ],
    ids=["asset context returns asset result and skip signal"],
)
def test_given_asset_context_when_building_results_then_returns_result_and_skip_models(
    test_case: PythonNodeContextHelperTestCase,
) -> None:
    adapter: PythonNodeContextTestAdapter = PythonNodeContextTestAdapter()
    context: AssetContext = build_asset_context(
        adapter=adapter,
        statement_recorder=StatementRecorder(),
        logger_name=test_case.expected_logger_name,
    )

    result: PythonNodeResult = context.result(
        payload=test_case.expected_execute_result,
        metadata={"format": "parquet"},
        materialized=False,
    )
    skip_result: PythonNodeSkipResult = context.skip(
        test_case.expected_query_result,
        mode=SkipMode.SELF,
        metadata={"cursor": "2026-05-30"},
    )

    assert result == PythonNodeResult(
        payload=test_case.expected_execute_result,
        metadata={"format": "parquet"},
        materialized=False,
    )
    assert skip_result == PythonNodeSkipResult(
        reason=test_case.expected_query_result,
        mode=SkipMode.SELF,
        metadata={"cursor": "2026-05-30"},
    )
    assert context.qualify_name(test_case.raw_name) == test_case.expected_qualified_name
    assert context.run_id == test_case.expected_run_id
    assert context.environment == test_case.expected_environment
    assert context.vars == test_case.expected_vars
    assert_base_context_fields(context)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeContextHelperTestCase(
            description="task context result omits materialized flag and loader-only fields",
            raw_name="scratch_orders",
            database=None,
            schema=None,
            expected_qualified_name="default_db.default_schema.scratch_orders",
            expected_execute_result="payload",
            expected_query_result="ignored",
            expected_recorded_events=(),
            expected_logger_name="sqlbuild.task.fetch_orders",
            expected_run_id="test_run",
            expected_environment="dev",
            expected_vars={"batch": "hourly"},
            expected_error_fragment="materialized",
        )
    ],
    ids=["task context result omits materialized flag and loader-only fields"],
)
def test_given_task_context_when_inspecting_api_then_loader_only_fields_are_absent(
    test_case: PythonNodeContextHelperTestCase,
) -> None:
    adapter: PythonNodeContextTestAdapter = PythonNodeContextTestAdapter()
    context: TaskContext = build_task_context(
        adapter=adapter,
        statement_recorder=StatementRecorder(),
        logger_name=test_case.expected_logger_name,
    )

    result: PythonNodeResult = context.result(
        payload=test_case.expected_execute_result,
        metadata={"source": "api"},
    )

    assert result == PythonNodeResult(
        payload=test_case.expected_execute_result,
        metadata={"source": "api"},
        materialized=None,
    )
    assert test_case.expected_error_fragment not in inspect.signature(context.result).parameters
    assert context.qualify_name(test_case.raw_name) == test_case.expected_qualified_name
    assert not hasattr(context, loader_only_attribute_names()[0])
    assert not hasattr(context, loader_only_attribute_names()[1])
    assert not hasattr(context, loader_only_attribute_names()[2])
    assert not hasattr(context, loader_only_attribute_names()[3])
    assert not hasattr(context, loader_only_attribute_names()[4])
    assert not hasattr(context, loader_only_attribute_names()[5])
    assert not hasattr(context, loader_only_attribute_names()[6])
    assert not hasattr(context, loader_only_attribute_names()[7])
