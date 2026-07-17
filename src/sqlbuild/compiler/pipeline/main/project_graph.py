"""Build a project graph from an already-compiled project."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.graph.main._build_lineage_downstream_deps import (
    build_lineage_downstream_deps,
)
from sqlbuild.compiler.graph.main._build_lineage_upstream_deps import (
    build_lineage_upstream_deps,
)
from sqlbuild.compiler.pipeline._helpers.graph import build_static_all_keys
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection._build_model_path_index import (
    build_model_path_index,
)
from sqlbuild.compiler.planner.main.selection._build_model_tag_index import (
    build_model_tag_index,
)


def build_project_graph_from_compiled_project(*, project: CompiledProject) -> ProjectGraph:
    """Build a static dependency graph for an already-compiled project."""

    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_upstream_deps(project)
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_downstream_deps(upstream_deps)
    )
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=downstream_deps,
        tag_index=build_model_tag_index(project),
        path_index=build_model_path_index(project),
        all_keys=build_static_all_keys(project),
    )
