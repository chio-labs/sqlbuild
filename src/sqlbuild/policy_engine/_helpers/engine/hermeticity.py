"""Static hermeticity verification for cacheable custom rules."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlbuild.policy_engine.constants import POLICY_DIRECTORY_NAME
from sqlbuild.policy_engine.exceptions import PolicyError
from sqlbuild.policy_engine.models import PolicyRule

_ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset(
    {"collections", "dataclasses", "enum", "policy", "math", "re", "sqlbuild.policy", "typing"}
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
_PROJECT_WIDE_CONTEXT_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "all_enum_declarations",
        "fault_for",
        "is_project_anchor",
        "policy_config",
        "project_dir",
        "project_glob",
        "project_read_text",
        "public_constants",
        "public_enums",
        "selected_rules",
    }
)
_CONTEXT_PARAMETER_NAME: str = "ctx"


def verify_custom_rules(*, rules: tuple[PolicyRule, ...], project_dir: Path) -> None:
    """Reject custom-rule source that can observe untracked process or filesystem state."""

    checked: set[Path] = set()
    for rule in rules:
        if not rule.custom or rule.source is None:
            continue
        source_path: Path = Path(rule.source).resolve()
        if not rule.project_wide:
            _verify_model_local_rule(rule=rule, path=source_path)
        source_root: Path = _source_root(source_path=source_path, project_dir=project_dir)
        paths: tuple[Path, ...] = tuple(sorted(source_root.rglob("*.py")))
        for path in paths:
            if path in checked:
                continue
            checked.add(path)
            _verify_source(path=path, project_dir=project_dir)


def _verify_model_local_rule(*, rule: PolicyRule, path: Path) -> None:
    source: str = path.read_text(encoding="utf-8")
    tree: ast.Module = ast.parse(source, filename=str(path))
    check_name: str = getattr(rule.check, "__name__", "")
    check: ast.FunctionDef | ast.AsyncFunctionDef | None = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == check_name
        ),
        None,
    )
    if check is None:
        raise PolicyError(f"custom policy check {check_name!r} is missing from {path}")
    for node in ast.walk(check):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == _CONTEXT_PARAMETER_NAME
            and node.attr in _PROJECT_WIDE_CONTEXT_ATTRIBUTES
        ):
            raise PolicyError(
                f"model-local custom policy rule {rule.code} at {path}:{node.lineno} "
                f"uses project-wide context {node.attr}; declare project_wide=True"
            )


def _source_root(*, source_path: Path, project_dir: Path) -> Path:
    root: Path = project_dir.resolve()
    for parent in (source_path.parent, *source_path.parents):
        if parent == root:
            break
        if parent.name == POLICY_DIRECTORY_NAME:
            return parent
    return source_path.parent


def _verify_source(*, path: Path, project_dir: Path) -> None:
    if not path.is_relative_to(project_dir.resolve()):
        raise PolicyError(f"custom policy source must be repository-owned: {path}")
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
                raise PolicyError(
                    f"non-hermetic custom policy rule at {path}:{node.lineno}: "
                    f"call to {call_name} must go through RuleContext"
                )


def _verify_import(*, path: Path, line: int, module: str) -> None:
    allowed: bool = any(
        module == root or module.startswith(f"{root}.") for root in _ALLOWED_IMPORT_ROOTS
    )
    if not allowed:
        raise PolicyError(
            f"non-hermetic custom policy rule at {path}:{line}: import {module!r} is not allowed"
        )


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
