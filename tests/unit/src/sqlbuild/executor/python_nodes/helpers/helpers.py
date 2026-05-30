"""Helpers for Python-node scheduler tests."""

from __future__ import annotations

import logging
from typing import Any, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.assets import AssetContext
from sqlbuild.checks import CheckContext
from sqlbuild.executor.python_nodes.models import BasePythonNodeContext, PythonNodeRunState
from sqlbuild.executor.shared.helpers.python_node_scheduler import unlock_downstream_python_nodes
from sqlbuild.tasks import TaskContext


def apply_completion_order(
    *,
    completion_order: tuple[str, ...],
    in_degree: dict[str, int],
    ready: list[str],
    downstream_names: dict[str, tuple[str, ...]],
) -> None:
    completed_node_name: str
    for completed_node_name in completion_order:
        unlock_downstream_python_nodes(
            completed_node_name=completed_node_name,
            in_degree=in_degree,
            ready=ready,
            downstream_names=downstream_names,
        )


class PythonNodeContextTestAdapter(BaseAdapter):
    """Adapter that records SQL and returns deterministic values."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> object:
        del connection
        self.executed_sql.append(sql)
        return f"result:{sql}"


def build_task_context(
    *,
    adapter: PythonNodeContextTestAdapter,
    statement_recorder: StatementRecorder,
    logger_name: str,
    run_state: PythonNodeRunState | None = None,
) -> TaskContext:
    return TaskContext(
        adapter=adapter,
        connection_config={"warehouse": "dev"},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={"batch": "hourly"},
        is_reload=False,
        logger=logging.getLogger(logger_name),
        statement_recorder=statement_recorder,
        run_state=run_state,
        default_database="default_db",
        default_schema="default_schema",
    )


def build_asset_context(
    *,
    adapter: PythonNodeContextTestAdapter,
    statement_recorder: StatementRecorder,
    logger_name: str,
    run_state: PythonNodeRunState | None = None,
) -> AssetContext:
    return AssetContext(
        adapter=adapter,
        connection_config={"warehouse": "dev"},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={"batch": "hourly"},
        is_reload=False,
        logger=logging.getLogger(logger_name),
        statement_recorder=statement_recorder,
        run_state=run_state,
        default_database="default_db",
        default_schema="default_schema",
    )


def build_check_context(
    *,
    adapter: PythonNodeContextTestAdapter,
    statement_recorder: StatementRecorder,
    logger_name: str,
    run_state: PythonNodeRunState | None = None,
) -> CheckContext:
    return CheckContext(
        adapter=adapter,
        connection_config={"warehouse": "dev"},
        connection=object(),
        run_id="test_run",
        environment="dev",
        vars={"batch": "hourly"},
        is_reload=False,
        logger=logging.getLogger(logger_name),
        statement_recorder=statement_recorder,
        run_state=run_state,
        default_database="default_db",
        default_schema="default_schema",
    )


def upstream_task(_ctx: object) -> object:
    return None


def skipped_upstream_task(_ctx: object) -> object:
    return None


def fetch_orders(ctx: TaskContext) -> object:
    return ctx.result(
        payload={"file": "orders.json"},
        metadata={"row_count": 3},
    )


def export_orders(ctx: AssetContext) -> object:
    payload: object = ctx.payload(fetch_orders)
    metadata: object = ctx.metadata(fetch_orders)
    if not isinstance(payload, dict) or not isinstance(metadata, dict):
        raise TypeError("Expected upstream payload and metadata dictionaries")
    payload_dict: dict[str, object] = cast(dict[str, object], payload)
    metadata_dict: dict[str, object] = cast(dict[str, object], metadata)
    file_name: object | None = payload_dict.get("file")
    if not isinstance(file_name, str):
        raise TypeError("Expected upstream file payload")
    return ctx.result(
        payload={"uri": f"s3://exports/{file_name}"},
        metadata=metadata_dict,
        materialized=True,
    )


def skip_empty_orders(ctx: TaskContext) -> object:
    return ctx.skip("No new orders")


def export_after_skip(ctx: AssetContext) -> object:
    return ctx.result(payload={"uri": "should-not-run"}, materialized=True)


def fail_orders(_ctx: TaskContext) -> object:
    raise RuntimeError("API unavailable")


def export_after_failure(ctx: AssetContext) -> object:
    return ctx.result(payload={"uri": "should-not-run"}, materialized=True)


class FlakyTask:
    def __init__(self, failures_before_success: int, exception_type: type[Exception]) -> None:
        self.failures_before_success: int = failures_before_success
        self.exception_type: type[Exception] = exception_type
        self.attempts: int = 0

    def __call__(self, ctx: TaskContext) -> object:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise self.exception_type("transient failure")
        return ctx.result(payload={"attempts": self.attempts})


def loader_only_attribute_names() -> tuple[str, ...]:
    return (
        "target",
        "target_database",
        "target_schema",
        "target_name",
        "current_cursor_value",
        "loader",
        "source",
        "qualify_in_target_schema",
    )


def assert_base_context_fields(context: BasePythonNodeContext) -> None:
    assert context.run_id == "test_run"
    assert context.environment == "dev"
    assert context.vars == {"batch": "hourly"}
    assert context.is_reload is False
    assert context.connection_config == {"warehouse": "dev"}
