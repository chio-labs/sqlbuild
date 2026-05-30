"""Helpers for Python-node scheduler tests."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.assets import AssetContext
from sqlbuild.executor.python_nodes.models import BasePythonNodeContext
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
        default_database="default_db",
        default_schema="default_schema",
    )


def build_asset_context(
    *,
    adapter: PythonNodeContextTestAdapter,
    statement_recorder: StatementRecorder,
    logger_name: str,
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
        default_database="default_db",
        default_schema="default_schema",
    )


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
