"""Static hermeticity verification for cacheable custom rules."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.models import Rule

_CONTEXT_TREE_CALLS: frozenset[str] = frozenset({"glob", "read_text"})

_ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "decimal",
        "enum",
        "functools",
        "graphlib",
        "itertools",
        "math",
        "pathlib",
        "re",
        "rules",
        "sqlbuild.rules",
        "statistics",
        "typing",
    }
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


def verify_custom_rules(*, rules: tuple[Rule, ...], project_dir: Path) -> None:
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
    rules_root: Path = project_dir.resolve() / "rules"
    return rules_root if source_path.is_relative_to(rules_root) else source_path.parent


def _verify_source(*, path: Path, project_dir: Path) -> None:
    if not path.is_relative_to(project_dir.resolve()):
        raise RulesError(f"custom rule source must be repository-owned: {path}")
    source: str = path.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _verify_import(path=path, line=node.lineno, module=alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                _verify_import(path=path, line=node.lineno, module=node.module or "")
        elif isinstance(node, ast.Call):
            call_name: str | None = _call_name(node.func)
            mediated: bool = (
                isinstance(node.func, ast.Attribute)
                and call_name in _CONTEXT_TREE_CALLS
                and _attribute_path(node.func).endswith(".project.tree." + str(call_name))
            )
            if call_name in _BANNED_CALLS and not mediated:
                raise RulesError(
                    f"non-hermetic custom rule at {path}:{node.lineno}: "
                    f"call to {call_name} must go through RuleContext"
                )


def _verify_import(*, path: Path, line: int, module: str) -> None:
    allowed: bool = any(
        module == root or module.startswith(f"{root}.") for root in _ALLOWED_IMPORT_ROOTS
    )
    if not allowed:
        raise RulesError(
            f"non-hermetic custom rule at {path}:{line}: import {module!r} is not allowed"
        )


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _attribute_path(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix: str = _attribute_path(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""
