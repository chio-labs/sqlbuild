"""Tests for source loader execution models."""

from __future__ import annotations

import logging

import pytest

from sqlbuild.adapter.shared.models import LifeCycleEvent, StatementRecorder
from sqlbuild.executor.load.models import LoaderContext
from tests.unit.src.sqlbuild.executor.load._test_types import LoaderContextHelperTestCase
from tests.unit.src.sqlbuild.executor.load.helpers import LoaderContextTestAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        LoaderContextHelperTestCase(
            description="records helper calls and qualifies names using target namespace",
            raw_name="scratch_orders",
            database="override_db",
            schema="override_schema",
            expected_qualified_name="override_db.override_schema.scratch_orders",
            expected_target_schema_name="target_db.target_schema.scratch_orders",
            expected_execute_result="result:CREATE TABLE scratch_orders AS SELECT 1",
            expected_query_result="result:SELECT * FROM scratch_orders",
            expected_recorded_events=(
                "CREATE TABLE scratch_orders AS SELECT 1",
                "SELECT * FROM scratch_orders",
                "loading scratch orders",
            ),
            expected_logger_name="sqlbuild.loader.raw_orders_loader",
        ),
    ],
    ids=["records helper calls and qualifies names using target namespace"],
)
def test_given_loader_context_when_using_helpers_then_records_and_qualifies_names(
    test_case: LoaderContextHelperTestCase,
) -> None:
    adapter: LoaderContextTestAdapter = LoaderContextTestAdapter()
    statement_recorder: StatementRecorder = StatementRecorder()
    context: LoaderContext = LoaderContext(
        adapter=adapter,
        connection=object(),
        target="target_db.target_schema.raw_orders",
        target_database="target_db",
        target_schema="target_schema",
        target_name="raw_orders",
        run_id="test_run",
        environment="dev",
        vars={},
        is_reload=False,
        current_cursor_value=None,
        logger=logging.getLogger(test_case.expected_logger_name),
        statement_recorder=statement_recorder,
    )

    execute_result: object = context.execute_sql("CREATE TABLE scratch_orders AS SELECT 1")
    query_result: object = context.query("SELECT * FROM scratch_orders")
    context.log("loading scratch orders")
    qualified_name: str = context.qualify_name(
        test_case.raw_name,
        database=test_case.database,
        schema=test_case.schema,
    )
    target_schema_name: str = context.qualify_in_target_schema(test_case.raw_name)
    already_qualified_name: str = context.qualify_name("custom.schema.table")

    assert execute_result == test_case.expected_execute_result
    assert query_result == test_case.expected_query_result
    assert qualified_name == test_case.expected_qualified_name
    assert target_schema_name == test_case.expected_target_schema_name
    assert already_qualified_name == "custom.schema.table"
    assert context.logger.name == test_case.expected_logger_name
    events: tuple[LifeCycleEvent, ...] = statement_recorder.snapshot()
    assert tuple(event.content for event in events) == test_case.expected_recorded_events
