"""Repository audit for mandatory raw statement boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

_AUDITED_ROOTS: tuple[str, ...] = ("adapter", "adapters", "virtual/state")
_RAW_RECEIVERS: frozenset[str] = frozenset({"client", "raw_connection", "raw_cursor"})
_STATEMENT_METHODS: frozenset[str] = frozenset({"execute", "executemany", "query"})
_APPROVED_BOUNDARIES: dict[str, frozenset[tuple[str, str]]] = {
    "adapter/contract/classes/observed_connection.py": frozenset(
        {
            ("ObservedConnection.execute", "execute"),
            ("ObservedConnection.executemany", "executemany"),
        }
    ),
    "adapter/contract/classes/observed_cursor.py": frozenset(
        {
            ("ObservedCursor.execute", "execute"),
            ("ObservedCursor.executemany", "executemany"),
        }
    ),
    "adapters/bigquery/classes/bigquery_connection.py": frozenset(
        {("_BigQueryConnection.query_job", "query")}
    ),
}
_RAW_FACTORY_METHODS: frozenset[str] = frozenset({"cursor"})


def _iter_functions(tree: ast.Module) -> tuple[tuple[str, ast.FunctionDef], ...]:
    functions: list[tuple[str, ast.FunctionDef]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            functions.append((node.name, node))
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, ast.FunctionDef):
                    functions.append((f"{node.name}.{member.name}", member))
    return tuple(functions)


def _expression_is_raw(*, expression: ast.expr, aliases: set[str]) -> bool:
    if isinstance(expression, ast.Name):
        return expression.id in _RAW_RECEIVERS or expression.id in aliases
    if isinstance(expression, ast.Attribute):
        return expression.attr in _RAW_RECEIVERS or _expression_is_raw(
            expression=expression.value, aliases=aliases
        )
    return (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr in _RAW_FACTORY_METHODS
        and _expression_is_raw(expression=expression.func.value, aliases=aliases)
    )


def _raw_aliases(*, function: ast.FunctionDef) -> set[str]:
    aliases: set[str] = set()
    for node in ast.walk(function):
        target: ast.expr | None = None
        value: ast.expr | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        if isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if (
            isinstance(target, ast.Name)
            and value is not None
            and _expression_is_raw(expression=value, aliases=aliases)
        ):
            aliases.add(target.id)
    return aliases


def _function_violations(
    *, relative_path: str, qualified_name: str, function: ast.FunctionDef
) -> tuple[str, ...]:
    aliases: set[str] = _raw_aliases(function=function)
    approved: frozenset[tuple[str, str]] = _APPROVED_BOUNDARIES.get(relative_path, frozenset())
    violations: list[str] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in _STATEMENT_METHODS:
            continue
        if not _expression_is_raw(expression=node.func.value, aliases=aliases):
            continue
        if (qualified_name, node.func.attr) not in approved:
            violations.append(f"{relative_path}:{node.lineno}")
    return tuple(violations)


def audit_raw_statement_calls(*, source_root: Path) -> tuple[str, ...]:
    """Return raw statement calls found outside the approved low-level modules."""

    violations: list[str] = []
    for relative_root in _AUDITED_ROOTS:
        for path in sorted((source_root / relative_root).rglob("*.py")):
            relative_path: str = path.relative_to(source_root).as_posix()
            tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for qualified_name, function in _iter_functions(tree):
                violations.extend(
                    _function_violations(
                        relative_path=relative_path,
                        qualified_name=qualified_name,
                        function=function,
                    )
                )
    return tuple(violations)
