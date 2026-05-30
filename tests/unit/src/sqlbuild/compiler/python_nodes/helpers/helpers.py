"""Helpers for internal Python-node helper tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.python_nodes.helpers.inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.shared.types import PythonCheckSeverity
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.source import SourceColumnEntry
from sqlbuild.tasks import task


def fetch_events(_ctx: object) -> list[dict[str, object]]:
    return []


def load_events(_ctx: object) -> list[dict[str, object]]:
    return []


def prepare_orders(_ctx: object) -> None:
    return None


@task(name="prepare_orders")
def imported_prepare_orders(_ctx: object) -> None:
    return None


def export_orders(_ctx: object) -> None:
    return None


def check_orders_export(_ctx: object) -> bool:
    return True


def build_orders_python_node_graph() -> PythonNodeGraph:
    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            loader_functions=(
                DiscoveredLoaderFunction(
                    file_path=Path("/project/loaders/events.py"),
                    relative_path=Path("loaders/events.py"),
                    name="load_events",
                    function=load_events,
                    depends_on=(prepare_orders,),
                ),
            ),
            task_functions=(
                DiscoveredTaskFunction(
                    file_path=Path("/project/tasks/orders.py"),
                    relative_path=Path("tasks/orders.py"),
                    name="prepare_orders",
                    function=prepare_orders,
                    tags=("orders", "daily"),
                ),
            ),
            asset_functions=(
                DiscoveredAssetFunction(
                    file_path=Path("/project/assets/orders.py"),
                    relative_path=Path("assets/orders.py"),
                    name="export_orders",
                    function=export_orders,
                    depends_on=(imported_prepare_orders,),
                    tags=("exports", "daily"),
                    columns=(
                        SourceColumnEntry(name="order_id", type="INTEGER"),
                        SourceColumnEntry(name="export_uri", type="VARCHAR"),
                    ),
                ),
            ),
            check_functions=(
                DiscoveredCheckFunction(
                    file_path=Path("/project/checks/orders.py"),
                    relative_path=Path("checks/orders.py"),
                    name="check_orders_export",
                    function=check_orders_export,
                    depends_on=(export_orders,),
                    severity=PythonCheckSeverity.WARN,
                    tags=("exports",),
                ),
            ),
        )
    )
