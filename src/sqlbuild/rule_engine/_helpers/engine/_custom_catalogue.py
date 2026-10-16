"""Import the project's custom rule modules and collect their `@rule` functions."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from sqlbuild._native import PYTHON_INIT_MODULE_STEM, Rule, RulesError
from sqlbuild.rule_engine._helpers.engine.definition import (
    resolve_rule_signature,
    rule_from_value,
)
from sqlbuild.rule_engine.constants import RULE_DECORATOR_TOKEN
from sqlbuild.runtime.user_code.main.user_code_spec import user_code_spec


def load_custom_rules(*, project_dir: Path) -> tuple[Rule, ...]:
    """Every custom rule declared under the project's `rules/` directory, in file order."""

    result: list[Rule] = []
    existing_modules: frozenset[str] = frozenset(sys.modules)
    repository_path: str = str(project_dir.resolve())
    sys.path.insert(0, repository_path)
    try:
        for file_path in sorted((project_dir / "rules").resolve().rglob("*.py")):
            if RULE_DECORATOR_TOKEN not in file_path.read_text(encoding="utf-8"):
                continue
            name: str = _rule_module_name(file_path=file_path, project_dir=project_dir)
            spec: ModuleSpec | None = user_code_spec(
                name=name, file_path=file_path, root=project_dir
            )
            if spec is None or spec.loader is None:
                raise RulesError(f"could not load rule file {file_path}")
            module: ModuleType = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as error:
                raise RulesError(f"could not import rule file {file_path}: {error}") from error
            finally:
                _ = sys.modules.pop(name, None)
            result.extend(_module_rules(module=module, source=file_path))
    finally:
        sys.path.remove(repository_path)
        _remove_loaded_project_modules(existing_modules=existing_modules, project_dir=project_dir)
    return tuple(result)


def _rule_module_name(*, file_path: Path, project_dir: Path) -> str:
    relative: Path = file_path.relative_to(project_dir.resolve()).with_suffix("")
    parts: tuple[str, ...] = relative.parts
    if parts[-1] == PYTHON_INIT_MODULE_STEM:
        parts = parts[:-1]
    return ".".join(parts)


def _module_rules(*, module: ModuleType, source: Path) -> tuple[Rule, ...]:
    rules: tuple[Rule, ...] = tuple(
        resolve_rule_signature(rule=rule)
        for value in vars(module).values()
        if getattr(value, "__module__", None) == module.__name__
        and (rule := rule_from_value(value=value)) is not None
    )
    return tuple(replace(rule, source=source.as_posix()) for rule in rules)


def _remove_loaded_project_modules(*, existing_modules: frozenset[str], project_dir: Path) -> None:
    for name in tuple(sys.modules):
        if name in existing_modules:
            continue
        module: object = sys.modules.get(name)
        source: object = getattr(module, "__file__", None)
        if isinstance(source, str) and Path(source).resolve().is_relative_to(project_dir.resolve()):
            _ = sys.modules.pop(name, None)
