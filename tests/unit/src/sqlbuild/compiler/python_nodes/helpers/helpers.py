"""Helpers for internal Python-node helper tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationTarget,
    CompiledSource,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.helpers.inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.refs import model, source
from sqlbuild.shared.models import SqlResourceRef
from sqlbuild.shared.types import PythonCheckSeverity
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry
from sqlbuild.tasks import task


def fetch_events(_ctx: object) -> list[dict[str, object]]:
    return []


def fetch_pages(_ctx: object) -> list[dict[str, object]]:
    return []


def load_events(_ctx: object) -> list[dict[str, object]]:
    return []


def raw_orders(_ctx: object) -> list[dict[str, object]]:
    return []


def prepare_orders(_ctx: object) -> None:
    return None


def summarize_orders(_ctx: object) -> None:
    return None


@task(name="prepare_orders")
def imported_prepare_orders(_ctx: object) -> None:
    return None


def export_orders(_ctx: object) -> None:
    return None


def check_orders_export(_ctx: object) -> bool:
    return True


def check_loaded_orders(_ctx: object) -> bool:
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


def build_sql_ref_python_node_graph(*, dependency: SqlResourceRef) -> PythonNodeGraph:
    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            task_functions=(
                DiscoveredTaskFunction(
                    file_path=Path("/project/tasks/orders.py"),
                    relative_path=Path("tasks/orders.py"),
                    name="profile_orders",
                    function=prepare_orders,
                    depends_on=(dependency,),
                ),
            ),
        )
    )


def build_sql_downstream_task_to_loader_python_node_graph() -> PythonNodeGraph:
    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            loader_functions=(
                DiscoveredLoaderFunction(
                    file_path=Path("/project/loaders/orders.py"),
                    relative_path=Path("loaders/orders.py"),
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
                    depends_on=(model_ref("orders"),),
                ),
            ),
        )
    )


def model_ref(name: str) -> SqlResourceRef:
    return model(name)


def source_ref(name: str) -> SqlResourceRef:
    return source(name)


def build_terminal_loader_task_dependency_python_node_graph() -> PythonNodeGraph:
    return _build_loader_dependency_python_node_graph(
        dependency_function=raw_orders,
        include_intermediate_loader=False,
        dependent_kind="task",
    )


def build_terminal_loader_asset_dependency_python_node_graph() -> PythonNodeGraph:
    return _build_loader_dependency_python_node_graph(
        dependency_function=raw_orders,
        include_intermediate_loader=False,
        dependent_kind="asset",
    )


def build_terminal_loader_check_dependency_python_node_graph() -> PythonNodeGraph:
    return _build_loader_dependency_python_node_graph(
        dependency_function=raw_orders,
        include_intermediate_loader=False,
        dependent_kind="check",
    )


def build_intermediate_loader_task_dependency_python_node_graph() -> PythonNodeGraph:
    return _build_loader_dependency_python_node_graph(
        dependency_function=fetch_pages,
        include_intermediate_loader=True,
        dependent_kind="task",
    )


def build_intermediate_loader_asset_dependency_python_node_graph() -> PythonNodeGraph:
    return _build_loader_dependency_python_node_graph(
        dependency_function=fetch_pages,
        include_intermediate_loader=True,
        dependent_kind="asset",
    )


def build_intermediate_loader_check_dependency_python_node_graph() -> PythonNodeGraph:
    return _build_loader_dependency_python_node_graph(
        dependency_function=fetch_pages,
        include_intermediate_loader=True,
        dependent_kind="check",
    )


def _build_loader_dependency_python_node_graph(
    *,
    dependency_function: Callable[..., object],
    include_intermediate_loader: bool,
    dependent_kind: str,
) -> PythonNodeGraph:
    loader_functions: tuple[DiscoveredLoaderFunction, ...]
    if include_intermediate_loader:
        loader_functions = (
            DiscoveredLoaderFunction(
                file_path=Path("/project/loaders/events.py"),
                relative_path=Path("loaders/events.py"),
                name="fetch_pages",
                function=fetch_pages,
            ),
            DiscoveredLoaderFunction(
                file_path=Path("/project/loaders/events.py"),
                relative_path=Path("loaders/events.py"),
                name="load_events",
                function=load_events,
                depends_on=(fetch_pages,),
            ),
        )
    else:
        loader_functions = (
            DiscoveredLoaderFunction(
                file_path=Path("/project/loaders/events.py"),
                relative_path=Path("loaders/events.py"),
                name="raw_orders",
                function=raw_orders,
            ),
        )

    task_functions: tuple[DiscoveredTaskFunction, ...] = ()
    asset_functions: tuple[DiscoveredAssetFunction, ...] = ()
    check_functions: tuple[DiscoveredCheckFunction, ...] = ()
    if dependent_kind == "task":
        task_functions = (
            DiscoveredTaskFunction(
                file_path=Path("/project/tasks/orders.py"),
                relative_path=Path("tasks/orders.py"),
                name="summarize_orders",
                function=summarize_orders,
                depends_on=(dependency_function,),
            ),
        )
    elif dependent_kind == "asset":
        asset_functions = (
            DiscoveredAssetFunction(
                file_path=Path("/project/assets/orders.py"),
                relative_path=Path("assets/orders.py"),
                name="export_orders",
                function=export_orders,
                depends_on=(dependency_function,),
            ),
        )
    else:
        check_functions = (
            DiscoveredCheckFunction(
                file_path=Path("/project/checks/orders.py"),
                relative_path=Path("checks/orders.py"),
                name="check_loaded_orders",
                function=check_loaded_orders,
                depends_on=(dependency_function,),
                severity=PythonCheckSeverity.ERROR,
            ),
        )

    return build_python_node_graph(
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            loader_functions=loader_functions,
            task_functions=task_functions,
            asset_functions=asset_functions,
            check_functions=check_functions,
        )
    )


def build_python_node_graph_for_case(case_name: str) -> PythonNodeGraph:
    if case_name == "terminal_loader_task_dependency":
        return build_terminal_loader_task_dependency_python_node_graph()
    if case_name == "terminal_loader_asset_dependency":
        return build_terminal_loader_asset_dependency_python_node_graph()
    if case_name == "terminal_loader_check_dependency":
        return build_terminal_loader_check_dependency_python_node_graph()
    if case_name == "intermediate_loader_task_dependency":
        return build_intermediate_loader_task_dependency_python_node_graph()
    if case_name == "intermediate_loader_asset_dependency":
        return build_intermediate_loader_asset_dependency_python_node_graph()
    if case_name == "intermediate_loader_check_dependency":
        return build_intermediate_loader_check_dependency_python_node_graph()
    return build_orders_python_node_graph()


def build_orders_project_graph() -> ProjectGraph:
    raw_orders_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name="raw_orders",
    )
    orders_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    source_file: DiscoveredSourceFile = DiscoveredSourceFile(
        file_path=Path("/project/sources/raw.yml"),
        relative_path=Path("sources/raw.yml"),
        contents="sources: []\n",
        source_entries=(),
    )
    raw_orders_source: CompiledSource = CompiledSource(
        key=raw_orders_key,
        deps=(),
        name="raw_orders",
        source_entry=SourceEntry(name="raw_orders", loader="raw_orders", managed=True),
        source_file=source_file,
    )
    orders_model: CompiledModel = CompiledModel(
        key=orders_key,
        deps=(raw_orders_key,),
        name="orders",
        relative_path=Path("models/orders.sql"),
        query_sql="select * from __source('raw_orders')",
        config=CompileModelConfig(values={"tags": ["daily"]}),
        target=CompiledRelationTarget(
            database=None,
            schema=None,
            name="orders",
            qualified_name="orders",
        ),
    )
    project: CompiledProject = CompiledProject(
        run_id="run-id",
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        models=(orders_model,),
        sources=(raw_orders_source,),
    )
    return ProjectGraph(
        project=project,
        upstream_deps={raw_orders_key: (), orders_key: (raw_orders_key,)},
        downstream_deps={raw_orders_key: (orders_key,), orders_key: ()},
        tag_index={"daily": frozenset({orders_key})},
        path_index={orders_key: ""},
        all_keys={"raw_orders": raw_orders_key, "orders": orders_key},
    )


def build_model_depends_on_intermediate_loader_project_graph() -> ProjectGraph:
    project_graph: ProjectGraph = build_orders_project_graph()
    orders_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    intermediate_loader_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.SOURCE,
        name="fetch_pages",
    )
    return ProjectGraph(
        project=project_graph.project,
        upstream_deps={
            **project_graph.upstream_deps,
            orders_key: (intermediate_loader_key,),
        },
        downstream_deps={
            intermediate_loader_key: (orders_key,),
            orders_key: (),
        },
        tag_index=project_graph.tag_index,
        path_index=project_graph.path_index,
        all_keys=project_graph.all_keys,
    )
