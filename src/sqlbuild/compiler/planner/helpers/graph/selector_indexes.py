"""Model selector index implementations."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.planner.constants import MODEL_SELECTOR_ROOT, MODEL_SELECTOR_ROOT_PREFIX


def build_model_tag_index_impl(
    project: CompiledProject,
) -> dict[str, frozenset[CompiledObjectKey]]:
    """Build a tag-to-keys lookup from compiled model configs."""

    index: dict[str, set[CompiledObjectKey]] = {}
    model: CompiledModel
    for model in project.models:
        tag: str
        for tag in _as_string_list(model.config.values.get("tags")):
            index.setdefault(tag, set()).add(model.key)
    return {tag: frozenset(keys) for tag, keys in index.items()}


def build_model_path_index_impl(project: CompiledProject) -> dict[CompiledObjectKey, str]:
    """Build a key-to-folder lookup from compiled model relative paths."""

    index: dict[CompiledObjectKey, str] = {}
    model: CompiledModel
    for model in project.models:
        parent: str = str(model.relative_path.parent).replace("\\", "/")
        index[model.key] = _strip_models_prefix(parent)
    return index


def _strip_models_prefix(path: str) -> str:
    if path.startswith(MODEL_SELECTOR_ROOT_PREFIX):
        return path[len(MODEL_SELECTOR_ROOT_PREFIX) :]
    if path == MODEL_SELECTOR_ROOT:
        return ""
    return path


def _as_string_list(value: object) -> list[str]:
    if isinstance(value, list | tuple):
        return [str(item) for item in value]
    return []
