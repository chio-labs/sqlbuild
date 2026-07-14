"""Public planner entrypoints for loader DAG helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.graph.loader_dag import (
    build_intermediate_source_map as _build_intermediate_source_map,
)
from sqlbuild.spec.contracts.models import SourceEntry


def build_intermediate_source_map(
    *, project: CompiledProject, selected_keys: frozenset[CompiledObjectKey]
) -> dict[str, SourceEntry]:
    """Return synthetic source entries for selected intermediate loader nodes."""

    return _build_intermediate_source_map(project=project, selected_keys=selected_keys)
