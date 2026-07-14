"""Public executor entrypoint for Python read-side SQL-read Python tracking."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.python_nodes._helpers.read_side_execution import (
    ReadSidePythonExecutionTracker,
)
from sqlbuild.executor.python_nodes.models import PythonNodeRuntime
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder


def create_read_side_python_execution_tracker(
    *,
    python_graph: PythonNodeGraph,
    selected_python_names: frozenset[str],
    runtime: PythonNodeRuntime,
    identity_recorder: PythonIdentityRecorder | None = None,
) -> ReadSidePythonExecutionTracker:
    """Create a read-side Python execution tracker."""

    return ReadSidePythonExecutionTracker(
        python_graph=python_graph,
        selected_python_names=selected_python_names,
        runtime=runtime,
        identity_recorder=identity_recorder,
    )
