"""Shared builders for tests that hand-assemble a project graph."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.graph.main._native_graph_from_views import native_graph_from_views
from sqlbuild.compiler.pipeline.models import ProjectGraph


def project_graph_from_indexes(
    *,
    project: CompiledProject,
    upstream_deps: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    downstream_deps: Mapping[CompiledObjectKey, Iterable[CompiledObjectKey]],
    tag_index: Mapping[str, Iterable[CompiledObjectKey]],
    path_index: Mapping[CompiledObjectKey, str],
    all_keys: Mapping[str, CompiledObjectKey],
) -> ProjectGraph:
    """A natively held graph over hand-built indexes, keeping their order."""

    return ProjectGraph(
        project=project,
        native=native_graph_from_views(
            all_keys=all_keys,
            upstream=upstream_deps,
            downstream=downstream_deps,
            tag_index=tag_index,
            path_index=path_index,
        ),
    )
