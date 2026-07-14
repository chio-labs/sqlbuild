"""Build the static SQLBuild DAG JSON artifact."""

from __future__ import annotations

from sqlbuild.compiler.dag._helpers.artifact import build_dag_artifact, format_dag_json
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph


def build_dag_json(
    *, graph: ProjectGraph, project_name: str, python_graph: PythonNodeGraph | None = None
) -> str:
    """Build and serialize a static SQLBuild DAG artifact."""

    return format_dag_json(
        artifact=build_dag_artifact(
            graph=graph,
            project_name=project_name,
            python_graph=python_graph,
        )
    )
