"""Public planner entrypoints for loader DAG helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner.helpers.graph.loader_dag import (
    build_intermediate_source_map as _build_intermediate_source_map,
)
from sqlbuild.spec.models.source import SourceEntry


def build_intermediate_source_map(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey]
) -> dict[str, SourceEntry]:
    """Return synthetic source entries for selected intermediate loader nodes."""

    return _build_intermediate_source_map(project=project, selected_keys=selected_keys)
