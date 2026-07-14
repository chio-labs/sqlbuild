"""Public entrypoint for run-command Python/SQL lifecycle planning."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes._helpers.run_lifecycle import (
    build_python_sql_run_lifecycle_plan,
)
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)


def build_python_sql_run_lifecycle(
    *, selection: PythonSqlRunSelection, python_graph: PythonNodeGraph
) -> PythonSqlRunLifecyclePlan:
    """Classify selected run nodes into lifecycle-aware execution regions."""

    return build_python_sql_run_lifecycle_plan(
        selection=selection,
        python_graph=python_graph,
    )
