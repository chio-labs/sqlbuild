"""Helpers for Python-node scheduler tests."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.assets import AssetContext
from sqlbuild.checks import CheckContext
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.python_nodes.helpers.inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes.helpers.run_lifecycle import (
    build_python_sql_run_lifecycle_plan,
)
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonNode,
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.executor.python_nodes.models import BasePythonNodeContext, PythonNodeRunState
from sqlbuild.executor.shared.helpers.python_node_scheduler import unlock_downstream_python_nodes
from sqlbuild.executor.shared.models.lifecycle_scheduler import LifecycleExecutionNode
from sqlbuild.refs import model
from sqlbuild.shared.types import PythonCheckSeverity
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.tasks import TaskContext
from tests.unit.src.sqlbuild.compiler.python_nodes.helpers.helpers import (
    build_intermediate_loader_asset_dependency_python_node_graph,
    build_orders_python_node_graph,
)


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


def cursor_window(ctx: TaskContext) -> object:
    return ctx.result(
        payload={
            "start_cursor_ts": ctx.start_cursor_ts,
            "end_cursor_ts": ctx.end_cursor_ts,
            "start_cursor_int": ctx.start_cursor_int,
            "end_cursor_int": ctx.end_cursor_int,
        }
    )


def export_after_failure(ctx: AssetContext) -> object:
    return ctx.result(payload={"uri": "should-not-run"}, materialized=True)


EXPECTED_START_CURSOR_TS: datetime = datetime(2026, 1, 1, tzinfo=UTC)
EXPECTED_END_CURSOR_TS: datetime = datetime(2026, 1, 2, tzinfo=UTC)


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


def build_lifecycle_plan_for_selected_python_names(
    *, graph: PythonNodeGraph, selected_names: frozenset[str]
) -> PythonSqlRunLifecyclePlan:
    return build_python_sql_run_lifecycle_plan(
        selection=PythonSqlRunSelection(sql_keys=frozenset(), python_node_names=selected_names),
        python_graph=graph,
    )


def lifecycle_node_payload_name(node: LifecycleExecutionNode) -> str:
    payload: object | None = node.payload
    assert isinstance(payload, DiscoveredPythonNode)
    return payload.name


def python_graph_for_lifecycle_case(case_name: str) -> PythonNodeGraph:
    if case_name == "orders":
        return build_orders_python_node_graph()
    if case_name == "intermediate_loader_asset_dependency":
        return build_intermediate_loader_asset_dependency_python_node_graph()
    raise ValueError(f"unknown lifecycle graph case: {case_name}")


INGRESS_CALLS: list[str] = []


def reset_ingress_calls() -> None:
    INGRESS_CALLS.clear()


def ingress_calls() -> tuple[str, ...]:
    return tuple(INGRESS_CALLS)


def prepare_ingress_orders(ctx: TaskContext) -> object:
    INGRESS_CALLS.append("prepare_ingress_orders")
    return ctx.result(payload={"prepared": True})


def load_ingress_orders(_ctx: object) -> object:
    INGRESS_CALLS.append("load_ingress_orders")
    return None


def build_ingress_task_loader_graph() -> PythonNodeGraph:
    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            loader_functions=(ingress_loader_function(),),
            task_functions=(ingress_task_function(),),
        )
    )


def ingress_task_function() -> DiscoveredTaskFunction:
    return DiscoveredTaskFunction(
        file_path=Path("/project/tasks/orders.py"),
        relative_path=Path("tasks/orders.py"),
        name="prepare_ingress_orders",
        function=prepare_ingress_orders,
    )


def ingress_loader_function() -> DiscoveredLoaderFunction:
    return DiscoveredLoaderFunction(
        file_path=Path("/project/loaders/orders.py"),
        relative_path=Path("loaders/orders.py"),
        name="load_ingress_orders",
        function=load_ingress_orders,
        depends_on=(prepare_ingress_orders,),
    )


def ingress_source_map() -> dict[str, SourceEntry]:
    return {
        "raw_orders": SourceEntry(
            name="raw_orders",
            loader="load_ingress_orders",
        )
    }


READ_SIDE_CALLS: list[str] = []


def reset_read_side_calls() -> None:
    READ_SIDE_CALLS.clear()


def read_side_calls() -> tuple[str, ...]:
    return tuple(READ_SIDE_CALLS)


def profile_stg_orders(ctx: TaskContext) -> object:
    READ_SIDE_CALLS.append("profile_stg_orders")
    return ctx.result(payload={"profiled": True})


def export_stg_profile(ctx: AssetContext) -> object:
    READ_SIDE_CALLS.append("export_stg_profile")
    return ctx.result(payload=ctx.payload(profile_stg_orders), materialized=False)


def build_read_side_sql_task_asset_graph() -> PythonNodeGraph:
    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            task_functions=(
                DiscoveredTaskFunction(
                    file_path=Path("/project/tasks/orders.py"),
                    relative_path=Path("tasks/orders.py"),
                    name="profile_stg_orders",
                    function=profile_stg_orders,
                    depends_on=(model("stg_orders"),),
                ),
            ),
            asset_functions=(
                DiscoveredAssetFunction(
                    file_path=Path("/project/assets/orders.py"),
                    relative_path=Path("assets/orders.py"),
                    name="export_stg_profile",
                    function=export_stg_profile,
                    depends_on=(profile_stg_orders,),
                ),
            ),
        )
    )


def check_upstream_task(_ctx: object) -> object:
    return {"rows": 3}


def passing_python_check(ctx: CheckContext) -> object:
    metadata: dict[str, object] = cast(dict[str, object], ctx.metadata(check_upstream_task))
    return ctx.pass_("passed", metadata={"rows": metadata["rows"]})


def warning_python_check(ctx: CheckContext) -> object:
    return ctx.warn("warned")


def false_python_check(_ctx: CheckContext) -> object:
    return False


def exception_python_check(_ctx: CheckContext) -> object:
    raise RuntimeError("check exploded")


def python_check_function_for_case(description: str) -> DiscoveredCheckFunction:
    function: Callable[..., object] = passing_python_check
    if "warning" in description:
        function = warning_python_check
    if "false" in description:
        function = false_python_check
    if "exception" in description:
        function = exception_python_check
    return DiscoveredCheckFunction(
        file_path=Path("/project/checks/orders.py"),
        relative_path=Path("checks/orders.py"),
        name="check_upstream_task",
        function=function,
        depends_on=(check_upstream_task,),
        severity=PythonCheckSeverity.ERROR,
    )


def build_python_check_graph(*, check_function: DiscoveredCheckFunction) -> PythonNodeGraph:
    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            task_functions=(
                DiscoveredTaskFunction(
                    file_path=Path("/project/tasks/orders.py"),
                    relative_path=Path("tasks/orders.py"),
                    name="upstream_task",
                    function=check_upstream_task,
                ),
            ),
            check_functions=(check_function,),
        )
    )
