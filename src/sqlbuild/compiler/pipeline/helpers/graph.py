"""Static compiled project graph helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
)
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_static_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return static lineage edges keyed by object key."""

    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    model: CompiledModel
    for model in project.models:
        upstream[model.key] = model.deps
    source: CompiledSource
    for source in project.sources:
        upstream[source.key] = source.deps
    seed: CompiledSeed
    for seed in project.seeds:
        upstream[seed.key] = seed.deps
    function: CompiledFunction
    for function in project.functions:
        upstream[function.key] = function.deps
    return _filter_lineage_deps(upstream)


def build_static_downstream_deps(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return downstream edges keyed by upstream object key."""

    downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    for key in upstream:
        downstream.setdefault(key, [])
    for key, dep_keys in upstream.items():
        for dep_key in dep_keys:
            downstream.setdefault(dep_key, []).append(key)
    return {
        key: tuple(sorted(values, key=lambda obj: (str(obj.resource_type), obj.name)))
        for key, values in downstream.items()
    }


def build_static_tag_index(project: CompiledProject) -> dict[str, frozenset[CompiledObjectKey]]:
    """Build a tag-to-keys lookup from compiled model configs."""

    index: dict[str, set[CompiledObjectKey]] = {}
    for model in project.models:
        for tag in _as_string_list(model.config.values.get("tags")):
            index.setdefault(tag, set()).add(model.key)
    return {tag: frozenset(keys) for tag, keys in index.items()}


def build_static_path_index(project: CompiledProject) -> dict[CompiledObjectKey, str]:
    """Build a key-to-folder lookup from compiled model relative paths."""

    index: dict[CompiledObjectKey, str] = {}
    for model in project.models:
        parent: str = str(model.relative_path.parent)
        index[model.key] = _strip_models_prefix(parent)
    return index


def build_static_all_keys(project: CompiledProject) -> dict[str, CompiledObjectKey]:
    """Build selector lookup keys for all named graph resources."""

    keys: dict[str, CompiledObjectKey] = {}
    for model in project.models:
        keys[model.name] = model.key
    for source in project.sources:
        keys[source.name] = source.key
    for seed in project.seeds:
        keys[seed.name] = seed.key
    for function in project.functions:
        keys[function.name] = function.key
    return keys


def _filter_lineage_deps(
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Remove virtual execution-order nodes that are not lineage dependencies."""

    return {
        key: tuple(dep for dep in deps if dep.resource_type != CompiledResourceType.SQL_TEST)
        for key, deps in upstream_deps.items()
        if key.resource_type != CompiledResourceType.SQL_TEST
    }


def _strip_models_prefix(path: str) -> str:
    if path.startswith("models/"):
        return path[len("models/") :]
    if path == "models":
        return ""
    return path


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return []
