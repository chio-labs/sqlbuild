"""Static project graph shared by compile-only and planning pipelines."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject


@dataclass(frozen=True)
class ProjectGraph:
    """Static compiled project graph without warehouse state."""

    project: CompiledProject
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    tag_index: dict[str, frozenset[CompiledObjectKey]]
    path_index: dict[CompiledObjectKey, str]
    all_keys: dict[str, CompiledObjectKey]
