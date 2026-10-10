"""Build a dbt-compatible manifest.json from a compiled project and its native graph."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.manifest._helpers.payload import build_manifest_payload
from sqlbuild.compiler.planner.models import PlanOutput


def build_graph_manifest(
    *,
    project: CompiledProject,
    plan_output: PlanOutput | None,
    project_name: str,
    adapter_type: str,
    graph: _native.NativeProjectGraph,
) -> dict[str, object]:
    """Build the manifest with parent and child maps read from the native lineage graph."""

    return build_manifest_payload(
        project=project,
        plan_output=plan_output,
        project_name=project_name,
        adapter_type=adapter_type,
        graph=graph,
    )
