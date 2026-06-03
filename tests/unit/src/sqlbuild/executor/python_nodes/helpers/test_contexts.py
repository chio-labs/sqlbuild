"""Tests for Python task and asset runtime contexts."""

from __future__ import annotations

import inspect
import logging

import pytest

from sqlbuild.adapter.shared.models import LifeCycleEvent, StatementRecorder
from sqlbuild.assets import AssetContext
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonNodeStatus, SkipMode
from sqlbuild.executor.python_nodes.models import (
    PythonNodeExecutionResult,
    PythonNodeResult,
    PythonNodeRunState,
    PythonNodeSkipResult,
)
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.refs import model, source
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.tasks import TaskContext
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    PythonNodeContextHelperTestCase,
    PythonNodeRunStateTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    PythonNodeContextTestAdapter,
    assert_base_context_fields,
    build_asset_context,
    build_task_context,
    loader_only_attribute_names,
    skipped_upstream_task,
    upstream_task,
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
            expected_target="dev",
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
    assert context.target == test_case.expected_target
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
            expected_target="dev",
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
        mode=SkipMode.SOFT,
        metadata={"cursor": "2026-05-30"},
    )

    assert result == PythonNodeResult(
        payload=test_case.expected_execute_result,
        metadata={"format": "parquet"},
        materialized=False,
    )
    assert skip_result == PythonNodeSkipResult(
        reason=test_case.expected_query_result,
        mode=SkipMode.SOFT,
        metadata={"cursor": "2026-05-30"},
    )
    assert context.qualify_name(test_case.raw_name) == test_case.expected_qualified_name
    assert context.run_id == test_case.expected_run_id
    assert context.target == test_case.expected_target
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
            expected_target="dev",
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


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeContextHelperTestCase(
            description="returns declared SQL relation and rejects undeclared SQL relation",
            raw_name="fact_orders",
            database=None,
            schema=None,
            expected_qualified_name="dev.fact_orders",
            expected_execute_result="raw.orders",
            expected_query_result="ignored",
            expected_recorded_events=(),
            expected_logger_name="sqlbuild.task.profile_orders",
            expected_run_id="test_run",
            expected_target="dev",
            expected_vars={"batch": "hourly"},
            expected_error_fragment="must be declared in depends_on before use",
        )
    ],
    ids=["returns declared SQL relation and rejects undeclared SQL relation"],
)
def test_given_task_context_when_resolving_sql_relations_then_validates_declared_refs(
    test_case: PythonNodeContextHelperTestCase,
) -> None:
    model_ref: SqlResourceRef = model(test_case.raw_name)
    source_ref: SqlResourceRef = source("orders")
    context: TaskContext = TaskContext(
        adapter=PythonNodeContextTestAdapter(),
        connection_config={"warehouse": "dev"},
        connection=object(),
        run_id=test_case.expected_run_id,
        target=test_case.expected_target,
        vars=test_case.expected_vars,
        is_reload=False,
        logger=logging.getLogger(test_case.expected_logger_name),
        statement_recorder=StatementRecorder(),
        default_database="default_db",
        default_schema="default_schema",
        relation_targets={
            model_ref: test_case.expected_qualified_name,
            source_ref: test_case.expected_execute_result,
        },
        allowed_sql_refs=frozenset((model_ref,)),
    )

    assert context.relation(model_ref) == test_case.expected_qualified_name
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        context.relation(source_ref)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeRunStateTestCase(
            description="reads same-run upstream payload and metadata",
            expected_payload={"file": "orders.json"},
            expected_metadata={"row_count": 3},
            expected_default={"fallback": True},
            expected_error_fragment="did not produce a successful payload",
        )
    ],
    ids=["reads same-run upstream payload and metadata"],
)
def test_given_context_with_run_state_when_reading_upstream_outputs_then_returns_values(
    test_case: PythonNodeRunStateTestCase,
) -> None:
    run_state: PythonNodeRunState = PythonNodeRunState()
    run_state.record_result(
        node_function=upstream_task,
        result=PythonNodeExecutionResult(
            node_name="upstream_task",
            kind=PythonNodeKind.TASK,
            status=PythonNodeStatus.SUCCESS,
            payload=test_case.expected_payload,
            metadata=test_case.expected_metadata,
        ),
    )
    run_state.record_result(
        node_function=skipped_upstream_task,
        result=PythonNodeExecutionResult(
            node_name="skipped_upstream_task",
            kind=PythonNodeKind.TASK,
            status=PythonNodeStatus.SKIPPED,
            skip_mode=SkipMode.HARD,
            skip_reason="No rows",
        ),
    )
    context: AssetContext = build_asset_context(
        adapter=PythonNodeContextTestAdapter(),
        statement_recorder=StatementRecorder(),
        logger_name="sqlbuild.asset.export_customers",
        run_state=run_state,
    )

    assert context.payload(upstream_task) == test_case.expected_payload
    assert context.metadata(upstream_task) == test_case.expected_metadata
    assert context.payload(lambda _ctx: None, default=test_case.expected_default) == (
        test_case.expected_default
    )
    assert context.metadata(lambda _ctx: None, default=test_case.expected_default) == (
        test_case.expected_default
    )
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        context.payload(skipped_upstream_task)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodeRunStateTestCase(
            description="raises when no same-run state is available",
            expected_payload=None,
            expected_metadata={},
            expected_default="fallback",
            expected_error_fragment="No Python node run state is available",
        )
    ],
    ids=["raises when no same-run state is available"],
)
def test_given_context_without_run_state_when_reading_payload_then_raises_or_returns_default(
    test_case: PythonNodeRunStateTestCase,
) -> None:
    context: TaskContext = build_task_context(
        adapter=PythonNodeContextTestAdapter(),
        statement_recorder=StatementRecorder(),
        logger_name="sqlbuild.task.fetch_orders",
    )

    assert context.payload(upstream_task, default=test_case.expected_default) == (
        test_case.expected_default
    )
    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        context.payload(upstream_task)
