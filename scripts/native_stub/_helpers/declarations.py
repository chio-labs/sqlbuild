"""Names a native stub promises exist at runtime."""

from __future__ import annotations

import ast

from scripts.native_stub.constants import PRIVATE_PREFIX, TYPING_ONLY_BASES


def runtime_declarations(stub_text: str) -> tuple[str, ...]:
    """Top-level stub names that exist at runtime, excluding typing-only declarations, sorted."""
    names: set[str] = set()
    for node in ast.parse(stub_text).body:
        names.update(_declared_names(node))
    return tuple(sorted(names))


def stub_drift(*, stub_text: str, registered: frozenset[str]) -> tuple[str, ...]:
    """Runtime declarations in the stub that the extension does not register, sorted."""
    return tuple(name for name in runtime_declarations(stub_text) if name not in registered)


def _declared_names(node: ast.stmt) -> tuple[str, ...]:
    if isinstance(node, ast.FunctionDef):
        return (node.name,)
    if isinstance(node, ast.ClassDef):
        return () if _typing_only_class(node) else (node.name,)
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return (node.target.id,)
    if isinstance(node, ast.Assign):
        return tuple(target.id for target in node.targets if isinstance(target, ast.Name))
    return ()


def _typing_only_class(node: ast.ClassDef) -> bool:
    if node.name.startswith(PRIVATE_PREFIX):
        return True
    return any(ast.unparse(base).rsplit(".", 1)[-1] in TYPING_ONLY_BASES for base in node.bases)
