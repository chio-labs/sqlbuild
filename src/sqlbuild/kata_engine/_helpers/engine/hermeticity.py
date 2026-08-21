"""Static hermeticity verification for cacheable custom rules."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlbuild.kata_engine.constants import KATA_DIRECTORY_NAME
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.models import KataRule

_ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {"collections", "dataclasses", "enum", "kata", "math", "re", "sqlbuild.kata", "typing"}
)
_BANNED_CALLS: frozenset[str] = frozenset(
    {
        "__import__",
        "compile",
        "eval",
        "exec",
        "input",
        "open",
        "exists",
        "glob",
        "iterdir",
        "read_bytes",
        "read_text",
        "rglob",
        "stat",
        "write_bytes",
        "write_text",
    }
)


def verify_custom_rules(*, rules: tuple[KataRule, ...], project_dir: Path) -> None:
    """Reject custom-rule source that can observe untracked process or filesystem state."""

    checked: set[Path] = set()
    for rule in rules:
        if not rule.custom or rule.source is None:
            continue
        source_path: Path = Path(rule.source).resolve()
        source_root: Path = _source_root(source_path=source_path, project_dir=project_dir)
        paths: tuple[Path, ...] = tuple(sorted(source_root.rglob("*.py")))
        for path in paths:
            if path in checked:
                continue
            checked.add(path)
            _verify_source(path=path, project_dir=project_dir)


def _source_root(*, source_path: Path, project_dir: Path) -> Path:
    root: Path = project_dir.resolve()
    for parent in (source_path.parent, *source_path.parents):
        if parent == root:
            break
        if parent.name == KATA_DIRECTORY_NAME:
            return parent
    return source_path.parent


def _verify_source(*, path: Path, project_dir: Path) -> None:
    if not path.is_relative_to(project_dir.resolve()):
        raise KataError(f"custom kata source must be repository-owned: {path}")
    source: str = path.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _verify_import(path=path, line=node.lineno, module=alias.name)
        elif isinstance(node, ast.ImportFrom):
            _verify_import(path=path, line=node.lineno, module=node.module or "")
        elif isinstance(node, ast.Call):
            call_name: str | None = _call_name(node.func)
            if call_name in _BANNED_CALLS:
                raise KataError(
                    f"non-hermetic custom kata rule at {path}:{node.lineno}: "
                    f"call to {call_name} must go through RuleContext"
                )


def _verify_import(*, path: Path, line: int, module: str) -> None:
    allowed: bool = any(
        module == root or module.startswith(f"{root}.") for root in _ALLOWED_IMPORT_ROOTS
    )
    if not allowed:
        raise KataError(
            f"non-hermetic custom kata rule at {path}:{line}: import {module!r} is not allowed"
        )


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
