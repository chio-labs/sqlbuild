"""Parent/child map construction for manifest graph relationships."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
)


def build_unique_id(*, key: CompiledObjectKey, project_name: str, project: CompiledProject) -> str:
    """Build a dbt-style unique_id from a CompiledObjectKey."""

    source_names: frozenset[str] = frozenset(s.name for s in project.sources)
    seed_names: frozenset[str] = frozenset(s.name for s in project.seeds)

    if key.name in source_names:
        return f"source.{project_name}.{key.name}"
    if key.name in seed_names:
        return f"seed.{project_name}.{key.name}"
    return f"model.{project_name}.{key.name}"


def build_parent_map(
    *,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    project_name: str,
    project: CompiledProject,
) -> dict[str, list[str]]:
    """Build the parent_map (node -> first-order parents)."""

    result: dict[str, list[str]] = {}
    key: CompiledObjectKey
    parents: tuple[CompiledObjectKey, ...]
    for key, parents in upstream_deps.items():
        node_id: str = build_unique_id(key=key, project_name=project_name, project=project)
        result[node_id] = [
            build_unique_id(key=parent, project_name=project_name, project=project)
            for parent in parents
        ]
    return result


def build_child_map(
    *,
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    project_name: str,
    project: CompiledProject,
) -> dict[str, list[str]]:
    """Build the child_map (node -> first-order children)."""

    result: dict[str, list[str]] = {}
    key: CompiledObjectKey
    children: tuple[CompiledObjectKey, ...]
    for key, children in downstream_deps.items():
        node_id: str = build_unique_id(key=key, project_name=project_name, project=project)
        result[node_id] = [
            build_unique_id(key=child, project_name=project_name, project=project)
            for child in children
        ]
    return result
