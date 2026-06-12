"""Public Python-node identity computation entrypoint."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from sqlbuild.compiler.python_nodes.helpers.identity import build_python_identity
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity


def build_python_node_identity(
    *,
    node_type: str,
    node_name: str,
    function: Callable[..., object],
    project_dir: Path,
    decorator_config: Mapping[str, object] | None = None,
) -> PythonNodeIdentity:
    """Build read-only identity metadata for one Python node callable."""

    return build_python_identity(
        node_type=node_type,
        node_name=node_name,
        function=function,
        project_dir=project_dir,
        decorator_config=decorator_config or {},
    )
