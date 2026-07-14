"""Static compiled project graph helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
)


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
