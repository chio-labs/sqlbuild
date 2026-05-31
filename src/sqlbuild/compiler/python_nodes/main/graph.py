"""Public Python-node graph construction entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.python_nodes.helpers.inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph


def build_discovered_python_node_graph(
    *, discovered_inputs: DiscoveredProjectInputs
) -> PythonNodeGraph:
    """Build the internal executable Python-node graph from discovered inputs."""

    return build_python_node_graph(discovered_inputs=discovered_inputs)
