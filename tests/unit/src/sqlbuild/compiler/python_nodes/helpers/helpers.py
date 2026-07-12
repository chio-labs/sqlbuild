"""Helpers for internal Python-node helper tests."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
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
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.helpers.inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.providers import Provider
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import PythonCheckSeverity
from sqlbuild.refs import model, source
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


class SlackProvider(Provider):
    channel: str = "#alerts"


def notify_orders(_ctx: object, slack_provider: SlackProvider) -> None:
    return None


def check_loaded_orders(_ctx: object) -> bool:
    return True


def build_external_loader_python_node_graph() -> PythonNodeGraph:
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
                    connection_mode=LoaderConnectionMode.EXTERNAL,
                ),
            ),
        )
    )


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


def write_python_identity_repo(*, project_dir: Path, repo_files: dict[str, str]) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in repo_files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")
    (project_dir / ".git").mkdir(exist_ok=True)


def load_python_identity_module(
    *, project_dir: Path, module_path: str, extra_sys_paths: tuple[str, ...] = ()
) -> ModuleType:
    file_path: Path = project_dir / module_path
    module_name: str = f"python_identity_{abs(hash((str(project_dir), module_path)))}"
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(
        module_name,
        file_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    original_path: list[str] = list(sys.path)
    _clear_project_modules(project_dir=project_dir)
    sys.path.insert(0, str(project_dir))
    extra_path: str
    for extra_path in reversed(extra_sys_paths):
        sys.path.insert(0, str(project_dir / extra_path))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    return module


def _clear_project_modules(*, project_dir: Path) -> None:
    top_level_names: set[str] = {
        path.stem if path.is_file() else path.name
        for path in project_dir.iterdir()
        if not path.name.startswith(".")
    }
    module_name: str
    for module_name in tuple(sys.modules):
        if any(
            module_name == top_level_name or module_name.startswith(f"{top_level_name}.")
            for top_level_name in top_level_names
        ):
            sys.modules.pop(module_name, None)


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
    if case_name == "external_loader":
        return build_external_loader_python_node_graph()
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
        destination=CompiledRelationLocation(
            database=None,
            schema=None,
            name="orders",
            qualified_name="orders",
        ),
    )
    project: CompiledProject = CompiledProject(
        run_id="run-id",
        effective_target_name=None,
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
