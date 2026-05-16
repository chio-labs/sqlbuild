"""Build the static SQLBuild DAG JSON artifact."""

from __future__ import annotations

from sqlbuild.compiler.dag.helpers.artifact import build_dag_artifact, format_dag_json
from sqlbuild.compiler.pipeline.models import ProjectGraph


def build_dag_json(*, graph: ProjectGraph, project_name: str) -> str:
    """Build and serialize a static SQLBuild DAG artifact."""

    return format_dag_json(artifact=build_dag_artifact(graph=graph, project_name=project_name))
