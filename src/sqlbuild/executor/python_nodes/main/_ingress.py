"""Public executor entrypoint for Python ingress loader nodes."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.python_nodes._helpers.ingress_execution import (
    execute_ingress_python_loader_nodes,
)
from sqlbuild.executor.python_nodes.models import (
    IngressCallbacks,
    PythonIngressLoaderExecutorResult,
    PythonNodeRuntime,
)
from sqlbuild.spec.contracts.models import SourceEntry


def run_ingress_python_loader_nodes(
    *,
    python_graph: PythonNodeGraph,
    selected_python_names: frozenset[str],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    source_map: Mapping[str, SourceEntry],
    runtime: PythonNodeRuntime,
    callbacks: IngressCallbacks | None = None,
) -> PythonIngressLoaderExecutorResult:
    """Execute Python ingress task/asset/loader nodes in lifecycle order."""

    return execute_ingress_python_loader_nodes(
        python_graph=python_graph,
        selected_python_names=selected_python_names,
        loader_functions=loader_functions,
        source_map=source_map,
        runtime=runtime,
        callbacks=callbacks,
    )
