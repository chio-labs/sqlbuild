"""Extract module, function, call, and dataclass facts from Python sources."""

from __future__ import annotations

import ast
import re

from scripts.dupscore._helpers.source_provider import module_name_for
from scripts.dupscore.models import ClassFact, FunctionFact, ModuleFacts, ProjectFacts

_IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DATACLASS_MARKER: str = "dataclass"
_MODEL_BASE_SUFFIXES: tuple[str, ...] = ("BaseModel", "NamedTuple", "TypedDict")


def extract_project_facts(sources: dict[str, str]) -> ProjectFacts:
    """Extract facts for every parseable module in the given sources."""

    modules: list[ModuleFacts] = []
    for relative_path in sorted(sources):
        module: str | None = module_name_for(relative_path)
        if module is None:
            continue
        parsed: ast.Module | None = _parse_module(sources[relative_path])
        if parsed is None:
            continue
        modules.append(
            _extract_module_facts(module=module, relative_path=relative_path, tree=parsed)
        )
    return ProjectFacts(modules=tuple(modules))


def _parse_module(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _extract_module_facts(*, module: str, relative_path: str, tree: ast.Module) -> ModuleFacts:
    imports: dict[str, str] = _collect_imports(tree)
    local_function_names: set[str] = {
        node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    functions: list[FunctionFact] = []
    classes: list[ClassFact] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(
                _extract_function_fact(
                    node=node,
                    module=module,
                    owner_prefix="",
                    imports=imports,
                    local_function_names=local_function_names,
                )
            )
        elif isinstance(node, ast.ClassDef):
            classes.append(
                _extract_class_fact(
                    node=node,
                    module=module,
                    imports=imports,
                    local_function_names=local_function_names,
                )
            )
    imported_modules: set[str] = set()
    for target in imports.values():
        imported_modules.add(target)
    return ModuleFacts(
        module=module,
        relative_path=relative_path,
        functions=tuple(functions),
        classes=tuple(classes),
        imported_modules=tuple(sorted(imported_modules)),
    )


def _collect_imports(tree: ast.Module) -> dict[str, str]:
    imports: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name: str = alias.asname or alias.name.split(".")[0]
                imports[local_name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            for alias in node.names:
                local_name = alias.asname or alias.name
                imports[local_name] = f"{node.module}.{alias.name}"
    return imports


def _extract_class_fact(
    *,
    node: ast.ClassDef,
    module: str,
    imports: dict[str, str],
    local_function_names: set[str],
) -> ClassFact:
    methods: list[FunctionFact] = []
    field_names: list[str] = []
    for statement in node.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(
                _extract_function_fact(
                    node=statement,
                    module=module,
                    owner_prefix=node.name + ".",
                    imports=imports,
                    local_function_names=local_function_names,
                )
            )
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            field_names.append(statement.target.id)
    return ClassFact(
        name=node.name,
        qualified_name=f"{module}::{node.name}",
        module=module,
        public=not node.name.startswith("_"),
        lineno=node.lineno,
        dataclass_like=_is_dataclass_like(node),
        field_names=tuple(field_names),
        methods=tuple(methods),
    )


def _is_dataclass_like(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        decorated: ast.expr = decorator.func if isinstance(decorator, ast.Call) else decorator
        dotted: str | None = _dotted_name(decorated)
        if dotted is not None and _DATACLASS_MARKER in dotted:
            return True
    for base in node.bases:
        base_name: str | None = _dotted_name(base)
        if base_name is not None and base_name.endswith(_MODEL_BASE_SUFFIXES):
            return True
    return False


def _extract_function_fact(
    *,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module: str,
    owner_prefix: str,
    imports: dict[str, str],
    local_function_names: set[str],
) -> FunctionFact:
    resolved_calls: set[str] = set()
    bare_attribute_calls: set[str] = set()
    for statement in node.body:
        for descendant in ast.walk(statement):
            if not isinstance(descendant, ast.Call):
                continue
            resolved, bare = _classify_call(
                call=descendant,
                module=module,
                imports=imports,
                local_function_names=local_function_names,
            )
            if resolved is not None:
                resolved_calls.add(resolved)
            if bare is not None:
                bare_attribute_calls.add(bare)
    body_dump: str = ast.dump(ast.Module(body=node.body, type_ignores=[]))
    body_tokens: frozenset[str] = frozenset(_IDENTIFIER_PATTERN.findall(body_dump))
    return FunctionFact(
        name=node.name,
        qualified_name=f"{module}::{owner_prefix}{node.name}",
        module=module,
        public=not node.name.startswith("_"),
        lineno=node.lineno,
        resolved_calls=tuple(sorted(resolved_calls)),
        bare_attribute_calls=tuple(sorted(bare_attribute_calls)),
        body_tokens=body_tokens,
    )


def _classify_call(
    *,
    call: ast.Call,
    module: str,
    imports: dict[str, str],
    local_function_names: set[str],
) -> tuple[str | None, str | None]:
    target: ast.expr = call.func
    if isinstance(target, ast.Name):
        if target.id in local_function_names:
            return f"{module}::{target.id}", None
        if target.id in imports and imports[target.id].startswith("sqlbuild"):
            imported_target: str = imports[target.id]
            owner, _, symbol = imported_target.rpartition(".")
            return f"{owner}::{symbol}", None
        return None, None
    if isinstance(target, ast.Attribute):
        receiver: str | None = _dotted_name(target.value)
        if receiver is not None:
            receiver_root: str = receiver.split(".")[0]
            if receiver_root in imports and imports[receiver_root].startswith("sqlbuild"):
                receiver_suffix: list[str] = receiver.split(".")[1:]
                full_target: str = ".".join([imports[receiver_root], *receiver_suffix, target.attr])
                owner, _, symbol = full_target.rpartition(".")
                return f"{owner}::{symbol}", None
        return None, target.attr
    return None, None


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base: str | None = _dotted_name(node.value)
        if base is None:
            return None
        return f"{base}.{node.attr}"
    return None
