"""Deterministic project-tree facts for custom rules."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import (
    Model,
    ProjectPath,
    RuleUsageError,
    project_tree_file_path,
    project_tree_paths,
    validate_project_relative,
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
        parent: Path = Path(path)
        return tuple(node for node in self._nodes if Path(node.value).parent == parent)

    def descendants(self, path: str = "") -> tuple[ProjectPath, ...]:
        prefix: str = f"{Path(path).as_posix().rstrip('/')}/" if path else ""
        return tuple(node for node in self._nodes if node.value.startswith(prefix))

    def glob(self, pattern: str) -> tuple[ProjectPath, ...]:
        validate_project_relative(pattern)
        return tuple(node for node in self._nodes if fnmatch.fnmatchcase(node.value, pattern))

    def relative_parts(self, *, path: Path | str, under: str = "") -> tuple[str, ...]:
        relative: Path = Path(path)
        if relative.is_absolute():
            try:
                relative = relative.resolve().relative_to(self._root)
            except ValueError as error:
                raise RuleUsageError(f"project path escapes the project: {path}") from error
        if under:
            try:
                relative = relative.relative_to(Path(under))
            except ValueError as error:
                raise RuleUsageError(f"project path {path} is not beneath {under}") from error
        return relative.parts

    def resources_under(self, path: str) -> tuple[Model, ...]:
        prefix: str = f"{Path(path).as_posix().rstrip('/')}/"
        return tuple(
            model
            for relative, model in sorted(self._resource_paths.items())
            if relative.startswith(prefix)
        )

    def read_text(self, path: str) -> str:
        file: str = project_tree_file_path(self._root, path)
        try:
            return Path(file).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuleUsageError(f"could not read project file {path}: {error}") from error


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
