"""Deterministic project-tree facts for custom rules."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.rule_engine.constants import PARENT_DIRECTORY_TOKEN
from sqlbuild.rule_engine.exceptions import RuleUsageError
from sqlbuild.rule_engine.models import Model, ProjectPath

_EXCLUDED_ROOTS: frozenset[str] = frozenset({".git", ".venv", "logs", "target", "venv"})
_TRACKED_TEXT_SUFFIXES: frozenset[str] = frozenset({".py", ".sql", ".toml", ".yaml", ".yml"})


class ProjectTree:
    """Deterministic compiler-owned view of supported project paths."""

    def __init__(self, *, project_dir: Path, project: CompiledProject) -> None:
        self._root: Path = project_dir.resolve()
        self._nodes: tuple[ProjectPath, ...] = self._discover()
        self._resource_paths: dict[str, Model] = {
            item.relative_path.as_posix(): public_model(item) for item in project.models
        }

    def paths(self) -> tuple[ProjectPath, ...]:
        return self._nodes

    def children(self, path: str = "") -> tuple[ProjectPath, ...]:
        parent: Path = Path(path)
        return tuple(node for node in self._nodes if Path(node.value).parent == parent)

    def descendants(self, path: str = "") -> tuple[ProjectPath, ...]:
        prefix: str = f"{Path(path).as_posix().rstrip('/')}/" if path else ""
        return tuple(node for node in self._nodes if node.value.startswith(prefix))

    def glob(self, pattern: str) -> tuple[ProjectPath, ...]:
        self._validate_relative(pattern)
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
        self._validate_relative(path)
        candidate: Path = (self._root / path).resolve()
        if not candidate.is_relative_to(self._root) or not candidate.is_file():
            raise RuleUsageError(f"project file does not exist: {path}")
        if candidate.suffix.lower() not in _TRACKED_TEXT_SUFFIXES:
            supported: str = ", ".join(sorted(_TRACKED_TEXT_SUFFIXES))
            raise RuleUsageError(
                f"compiler rules input must be a tracked file type ({supported}): {path}"
            )
        if candidate.is_symlink():
            raise RuleUsageError(f"project file must not be a symlink: {path}")
        try:
            return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise RuleUsageError(f"could not read project file {path}: {error}") from error

    def _discover(self) -> tuple[ProjectPath, ...]:
        nodes: list[ProjectPath] = []
        for root, directories, filenames in os.walk(self._root, followlinks=False):
            root_path: Path = Path(root)
            directories[:] = sorted(
                name
                for name in directories
                if not name.startswith(".")
                and not (root_path == self._root and name in _EXCLUDED_ROOTS)
                and not (root_path / name).is_symlink()
            )
            for name in directories:
                relative: str = (root_path / name).relative_to(self._root).as_posix()
                nodes.append(ProjectPath(value=relative, is_file=False, is_dir=True))
            for name in sorted(filenames):
                file_path: Path = root_path / name
                if file_path.is_symlink():
                    continue
                relative = file_path.relative_to(self._root).as_posix()
                nodes.append(ProjectPath(value=relative, is_file=True, is_dir=False))
        return tuple(sorted(nodes))

    @staticmethod
    def _validate_relative(path: str) -> None:
        candidate: Path = Path(path)
        if candidate.is_absolute() or PARENT_DIRECTORY_TOKEN in candidate.parts:
            raise RuleUsageError(f"project path escapes the project: {path}")


def public_model(model: object) -> Model:
    from sqlbuild.compiler.compile.models import CompiledModel

    if not isinstance(model, CompiledModel):
        raise RuleUsageError("model is not a compiled SQL model")
    value: object = model.config.values.get("materialized")
    return Model(
        name=model.name,
        path=model.relative_path,
        materialization=value if isinstance(value, str) else None,
    )
