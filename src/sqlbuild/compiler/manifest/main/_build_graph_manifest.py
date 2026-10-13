"""Build a dbt-compatible manifest.json from a compiled project and its native graph."""

from __future__ import annotations

from datetime import UTC, datetime

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.main._hook_identities import build_hook_identities


def build_graph_manifest(
    *,
    project: CompiledProjectView,
    plan_output: PlanOutput | None,
    project_name: str,
    adapter_type: str,
    graph: _native.NativeProjectGraph,
) -> _native.NativeManifest:
    """Build the manifest with parent and child maps read from the native lineage graph."""

    return _native.build_manifest(
        project=project,
        plan_output=plan_output,
        graph=graph,
        facts={
            "project_name": project_name,
            "adapter_type": adapter_type,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "hook_identities": build_hook_identities(project.hook_functions),
        },
    )
