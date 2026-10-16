"""Deterministic project-tree facts for custom rules."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import (
    Model,
    ProjectPath,
    RuleUsageError,
    project_tree_child_nodes,
    project_tree_descendant_nodes,
    project_tree_glob_nodes,
    project_tree_paths,
    project_tree_read_text,
    project_tree_relative_parts,
)
from sqlbuild.compiler.compile.types import CompiledProjectView


class ProjectTree:
    """Deterministic compiler-owned view of supported project paths."""

    def __init__(
        self,
        *,
        project_dir: Path,
        project: CompiledProjectView,
        models: tuple[Model, ...] | None = None,
    ) -> None:
        self._root: Path = project_dir.resolve()
        self._discovered: tuple[ProjectPath, ...] | None = None
        model_views: tuple[Model, ...] = (
            tuple(public_model(item) for item in project.models) if models is None else models
        )
        self._resource_paths: dict[str, Model] = {
            item.path.as_posix(): item for item in model_views
        }

    @property
    def _nodes(self) -> tuple[ProjectPath, ...]:
        if self._discovered is None:
            self._discovered = project_tree_paths(self._root)
        return self._discovered

    def paths(self) -> tuple[ProjectPath, ...]:
        return self._nodes

    def children(self, path: str = "") -> tuple[ProjectPath, ...]:
        return project_tree_child_nodes(self._nodes, path)

    def descendants(self, path: str = "") -> tuple[ProjectPath, ...]:
        return project_tree_descendant_nodes(self._nodes, path)

    def glob(self, pattern: str) -> tuple[ProjectPath, ...]:
        return project_tree_glob_nodes(self._nodes, pattern)

    def relative_parts(self, *, path: Path | str, under: str = "") -> tuple[str, ...]:
        return project_tree_relative_parts(root=self._root, path=path, under=under)

    def resources_under(self, path: str) -> tuple[Model, ...]:
        prefix: str = f"{Path(path).as_posix().rstrip('/')}/"
        return tuple(
            model
            for relative, model in sorted(self._resource_paths.items())
            if relative.startswith(prefix)
        )

    def read_text(self, path: str) -> str:
        return project_tree_read_text(self._root, path)


def public_model(model: object) -> Model:
    from sqlbuild._native import CompiledModel

    if not isinstance(model, (CompiledModel, _native.NativeCompiledModel)):
        raise RuleUsageError("model is not a compiled SQL model")
    value: object = model.config.values.get("materialized")
    return Model(
        name=model.name,
        path=model.relative_path,
        materialization=value if isinstance(value, str) else None,
    )
