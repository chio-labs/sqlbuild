"""Build a dbt-compatible manifest.json from compiled project state."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.graph.main._native_graph_from_edges import native_graph_from_edges
from sqlbuild.compiler.manifest._helpers.payload import build_manifest_payload
from sqlbuild.compiler.planner.models import PlanOutput


def build_manifest(
    *,
    project: CompiledProject,
    plan_output: PlanOutput | None = None,
    project_name: str,
    adapter_type: str,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[str, object]:
    """Build a full dbt v12-compatible manifest dictionary from caller-built edge maps."""

    graph: _native.NativeProjectGraph = native_graph_from_edges(
        upstream=upstream_deps, downstream=downstream_deps
    )
    return build_manifest_payload(
        project=project,
        plan_output=plan_output,
        project_name=project_name,
        adapter_type=adapter_type,
        graph=graph,
    )
