"""Shared model tag/path selector index builders."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
)

_MODELS_DIR_PREFIX: str = "models/"


def build_model_tag_index(project: CompiledProject) -> dict[str, frozenset[CompiledObjectKey]]:
    """Build a tag-to-keys lookup from compiled model configs."""

    index: dict[str, set[CompiledObjectKey]] = {}
    model: CompiledModel
    for model in project.models:
        tag: str
        for tag in _as_string_list(model.config.values.get("tags")):
            index.setdefault(tag, set()).add(model.key)
    return {tag: frozenset(keys) for tag, keys in index.items()}


def build_model_path_index(project: CompiledProject) -> dict[CompiledObjectKey, str]:
    """Build a key-to-folder lookup from compiled model relative paths."""

    index: dict[CompiledObjectKey, str] = {}
    model: CompiledModel
    for model in project.models:
        parent: str = str(model.relative_path.parent).replace("\\", "/")
        index[model.key] = _strip_models_prefix(parent)
    return index


def _strip_models_prefix(path: str) -> str:
    """Strip leading models/ from a relative path string."""

    if path.startswith(_MODELS_DIR_PREFIX):
        return path[len(_MODELS_DIR_PREFIX) :]
    if path == "models":
        return ""
    return path


def _as_string_list(value: object) -> list[str]:
    """Coerce a value to a list of strings."""

    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []
