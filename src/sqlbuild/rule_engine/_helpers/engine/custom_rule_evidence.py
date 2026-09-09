"""Static custom-rule test evidence and source fingerprinting."""

from __future__ import annotations

import ast
import hashlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlbuild.rule_engine.models import Rule

_PUBLIC_HARNESS_MODULES: frozenset[str] = frozenset({"sqlbuild.rules", "sqlbuild.rules.testing"})
_INIT_MODULE_NAME: str = "__init__"
_RULES_DIRECTORY_NAME: str = "rules"
_MIN_PARAMETRIZE_ARGUMENTS: int = 2
_PARAMETRIZE_ATTRIBUTE: str = "parametrize"
_PYTEST_MARK_ATTRIBUTE: str = "mark"
_PYTEST_MODULE_NAME: str = "pytest"
_PROJECT_FACT_ATTRIBUTES: frozenset[str] = frozenset(
    {"audits", "declarations", "graph", "project", "tests"}
)


@dataclass(frozen=True, order=True)
class _RuleTestEvidence:
    path: str
    line: int
    column: int
    owner: str


def custom_rule_test_evidence(*, rule: Rule, project_dir: Path) -> tuple[_RuleTestEvidence, ...]:
    """Return statically associated public-harness cases for one exact custom rule."""

    if rule.source is None:
        return ()
    source_path: Path = Path(rule.source).resolve()
    rule_module_names: frozenset[str] = _module_names(path=source_path, project_dir=project_dir)
    check_name: str = getattr(rule.check, "__name__", "")
    evidence: set[_RuleTestEvidence] = set()
    for path in sorted(project_dir.glob("tests/**/*.py")):
        if not (path.name.startswith("test_") or path.name.endswith("_test.py")):
            continue
        evidence.update(
            _file_evidence(
                path=path,
                project_dir=project_dir,
                rule_module_names=rule_module_names,
                check_name=check_name,
            )
        )
    return tuple(sorted(evidence))


def custom_rule_import_closure(*, rule: Rule, project_dir: Path) -> tuple[Path, ...]:
    """Return repository-owned helper files imported by one rule module."""

    if rule.source is None:
        return ()
    return _import_closure(
        source_path=Path(rule.source).resolve(), project_dir=project_dir.resolve()
    )


def custom_rule_implementation_fingerprint(
    *, rule: Rule, project_dir: Path, import_closure: tuple[Path, ...] | None = None
) -> str:
    """Fingerprint one rule function and its repository-owned imported helper closure."""

    digest: Any = hashlib.sha256()
    if rule.source is None:
        digest.update(inspect.getsource(rule.check).encode())
        return digest.hexdigest()
    digest.update(inspect.getsource(rule.check).encode())
    root: Path = project_dir.resolve()
    closure: tuple[Path, ...] = (
        custom_rule_import_closure(rule=rule, project_dir=root)
        if import_closure is None
        else import_closure
    )
    for path in closure:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def custom_rule_project_fact_attributes(
    *, rule: Rule, project_dir: Path, import_closure: tuple[Path, ...] | None = None
) -> frozenset[str]:
    """Return project-wide context attributes used by implementation or helper code."""

    if rule.project_wide:
        return frozenset({"project"})
    if rule.source is None:
        sources: tuple[str, ...] = (inspect.getsource(rule.check),)
    else:
        helper_paths: tuple[Path, ...] = (
            _import_closure(
                source_path=Path(rule.source).resolve(), project_dir=project_dir.resolve()
            )
            if import_closure is None
            else import_closure
        )
        sources = (
            inspect.getsource(rule.check),
            *(path.read_text(encoding="utf-8") for path in helper_paths),
        )
    attributes: set[str] = set()
    for source in sources:
        tree: ast.Module = ast.parse(source)
        attributes.update(
            node.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in _PROJECT_FACT_ATTRIBUTES
        )
    return frozenset(attributes)


def _import_closure(*, source_path: Path, project_dir: Path) -> tuple[Path, ...]:
    pending: list[Path] = [source_path]
    visited: set[Path] = {source_path}
    helpers: set[Path] = set()
    while pending:
        current: Path = pending.pop()
        try:
            tree: ast.Module = ast.parse(current.read_text(encoding="utf-8"), filename=str(current))
        except (OSError, UnicodeError, SyntaxError):
            continue
        for node in tree.body:
            candidate: Path | None = _local_import_path(
                node=node,
                source_path=current,
                project_dir=project_dir,
            )
            if candidate is None or candidate in visited:
                continue
            visited.add(candidate)
            helpers.add(candidate)
            pending.append(candidate)
    return tuple(sorted(helpers))


def _local_import_path(*, node: ast.stmt, source_path: Path, project_dir: Path) -> Path | None:
    module: str | None = None
    base: Path
    level: int = 0
    if isinstance(node, ast.ImportFrom):
        module = node.module
        level = node.level
        if node.level:
            base = source_path.parent
            for _ in range(node.level - 1):
                base = base.parent
        else:
            base = project_dir
    elif isinstance(node, ast.Import) and len(node.names) == 1:
        module = node.names[0].name
        base = project_dir
    else:
        return None
    if module is None:
        return None
    parts: tuple[str, ...] = tuple(module.split("."))
    if not level and (not parts or parts[0] != _RULES_DIRECTORY_NAME):
        return None
    candidate: Path = base.joinpath(*parts)
    file_candidate: Path = candidate.with_suffix(".py")
    package_candidate: Path = candidate / "__init__.py"
    resolved: Path | None = file_candidate if file_candidate.is_file() else None
    if resolved is None and package_candidate.is_file():
        resolved = package_candidate
    if resolved is None:
        return None
    resolved = resolved.resolve()
    return resolved if resolved.is_relative_to(project_dir) else None


def _file_evidence(
    *, path: Path, project_dir: Path, rule_module_names: frozenset[str], check_name: str
) -> set[_RuleTestEvidence]:
    try:
        tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return set()
    imports: dict[str, tuple[str, str | None]] = _imports(tree=tree)
    assignments: dict[str, ast.expr] = _assignments(tree.body)
    constructors: frozenset[str] = _constructors(tree=tree, imports=imports)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    relative_path: str = path.relative_to(project_dir).as_posix()
    found: set[_RuleTestEvidence] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_imported_symbol(
            expression=node.func,
            imports=imports,
            modules=_PUBLIC_HARNESS_MODULES,
            symbol="evaluate_rule",
        ):
            continue
        owner: ast.FunctionDef | ast.AsyncFunctionDef | None = _test_owner(
            node=node, parents=parents
        )
        if (
            owner is None
            or _is_statically_dead(node=node, owner=owner, parents=parents)
            or _is_statically_skipped(owner=owner, imports=imports, parents=parents)
        ):
            continue
        rule_argument: ast.expr | None = _keyword(call=node, name="rule")
        case_argument: ast.expr | None = _keyword(call=node, name="test_case")
        if (
            rule_argument is None
            or case_argument is None
            or not _is_imported_symbol(
                expression=rule_argument,
                imports=imports,
                modules=rule_module_names,
                symbol=check_name,
            )
        ):
            continue
        owner_name: str = f"{relative_path}:{owner.name}"
        for case in _case_declarations(
            expression=case_argument,
            owner=owner,
            imports=imports,
            assignments=assignments,
            constructors=constructors,
        ):
            found.add(
                _RuleTestEvidence(
                    path=relative_path,
                    line=case.lineno,
                    column=case.col_offset + 1,
                    owner=owner_name,
                )
            )
    return found


def _case_declarations(
    *,
    expression: ast.expr,
    owner: ast.FunctionDef | ast.AsyncFunctionDef,
    imports: dict[str, tuple[str, str | None]],
    assignments: dict[str, ast.expr],
    constructors: frozenset[str],
) -> tuple[ast.Call, ...]:
    direct: tuple[ast.Call, ...] = _declared_cases(
        expression=expression,
        field=None,
        imports=imports,
        assignments=assignments,
        constructors=constructors,
        seen=frozenset(),
    )
    if direct:
        return direct
    parameter: str | None = None
    field: str | None = None
    if isinstance(expression, ast.Name):
        parameter = expression.id
    elif isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
        parameter = expression.value.id
        field = expression.attr
    if parameter is None:
        return ()
    values: ast.expr | None = _parametrized_values(
        owner=owner, parameter=parameter, imports=imports
    )
    if values is None:
        return ()
    return _declared_cases(
        expression=values,
        field=field,
        imports=imports,
        assignments=assignments,
        constructors=constructors,
        seen=frozenset(),
    )


def _declared_cases(
    *,
    expression: ast.expr,
    field: str | None,
    imports: dict[str, tuple[str, str | None]],
    assignments: dict[str, ast.expr],
    constructors: frozenset[str],
    seen: frozenset[str],
) -> tuple[ast.Call, ...]:
    if (
        isinstance(expression, ast.Name)
        and expression.id in assignments
        and expression.id not in seen
    ):
        return _declared_cases(
            expression=assignments[expression.id],
            field=field,
            imports=imports,
            assignments=assignments,
            constructors=constructors,
            seen=seen | {expression.id},
        )
    if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
        cases: list[ast.Call] = []
        for item in expression.elts:
            cases.extend(
                _declared_cases(
                    expression=item,
                    field=field,
                    imports=imports,
                    assignments=assignments,
                    constructors=constructors,
                    seen=seen,
                )
            )
        return tuple(cases)
    if not isinstance(expression, ast.Call):
        return ()
    if field is None and _is_imported_symbol(
        expression=expression.func,
        imports=imports,
        modules=_PUBLIC_HARNESS_MODULES,
        symbol="RuleCase",
    ):
        return (expression,)
    if field is None:
        return ()
    if not isinstance(expression.func, ast.Name) or expression.func.id not in constructors:
        return ()
    value: ast.expr | None = next(
        (keyword.value for keyword in expression.keywords if keyword.arg == field), None
    )
    if value is None:
        return ()
    return _declared_cases(
        expression=value,
        field=None,
        imports=imports,
        assignments=assignments,
        constructors=constructors,
        seen=seen,
    )


def _parametrized_values(
    *,
    owner: ast.FunctionDef | ast.AsyncFunctionDef,
    parameter: str,
    imports: dict[str, tuple[str, str | None]],
) -> ast.expr | None:
    for decorator in owner.decorator_list:
        if not isinstance(decorator, ast.Call) or not _is_parametrize_call(
            expression=decorator.func, imports=imports
        ):
            continue
        if len(decorator.args) < _MIN_PARAMETRIZE_ARGUMENTS or not _parameter_names(
            decorator.args[0]
        ) == (parameter,):
            continue
        return decorator.args[1]
    return None


def _imports(tree: ast.Module) -> dict[str, tuple[str, str | None]]:
    result: dict[str, tuple[str, str | None]] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result[alias.asname or alias.name.split(".")[0]] = (alias.name, None)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            for alias in node.names:
                result[alias.asname or alias.name] = (node.module, alias.name)
    return result


def _assignments(statements: list[ast.stmt]) -> dict[str, ast.expr]:
    result: dict[str, ast.expr] = {}
    for statement in statements:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            value: ast.expr | None = statement.value
            targets: list[ast.expr] = (
                statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            )
            if value is not None:
                for target in targets:
                    if isinstance(target, ast.Name):
                        result[target.id] = value
    return result


def _constructors(
    *, tree: ast.Module, imports: dict[str, tuple[str, str | None]]
) -> frozenset[str]:
    declared: set[str] = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    declared.update(name for name, (_, symbol) in imports.items() if symbol is not None)
    return frozenset(declared)


def _is_imported_symbol(
    *,
    expression: ast.expr,
    imports: dict[str, tuple[str, str | None]],
    modules: frozenset[str],
    symbol: str,
) -> bool:
    if isinstance(expression, ast.Name):
        imported: tuple[str, str | None] | None = imports.get(expression.id)
        return imported is not None and imported[0] in modules and imported[1] == symbol
    if isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
        imported = imports.get(expression.value.id)
        if imported is None or expression.attr != symbol:
            return False
        module, imported_name = imported
        qualified_module: str = module if imported_name is None else f"{module}.{imported_name}"
        return qualified_module in modules
    return False


def _test_owner(
    *, node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    current: ast.AST = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.Lambda, ast.ClassDef)):
            return None
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not current.name.startswith("test_"):
                return None
            parent: ast.AST | None = parents.get(current)
            if isinstance(parent, ast.Module):
                return current
            if (
                isinstance(parent, ast.ClassDef)
                and parent.name.startswith("Test")
                and isinstance(parents.get(parent), ast.Module)
            ):
                return current
            return None
    return None


def _is_statically_skipped(
    *,
    owner: ast.FunctionDef | ast.AsyncFunctionDef,
    imports: dict[str, tuple[str, str | None]],
    parents: dict[ast.AST, ast.AST],
) -> bool:
    declarations: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = [owner]
    parent: ast.AST | None = parents.get(owner)
    if isinstance(parent, ast.ClassDef):
        declarations.append(parent)
    for declaration in declarations:
        for decorator in declaration.decorator_list:
            target: ast.expr = decorator.func if isinstance(decorator, ast.Call) else decorator
            if _is_pytest_mark(expression=target, imports=imports, mark="skip"):
                return True
            if not isinstance(decorator, ast.Call) or not _is_pytest_mark(
                expression=decorator.func, imports=imports, mark="skipif"
            ):
                continue
            condition: ast.expr | None = (
                decorator.args[0] if decorator.args else _keyword(call=decorator, name="condition")
            )
            if isinstance(condition, ast.Constant) and condition.value is True:
                return True
    return False


def _is_statically_dead(
    *,
    node: ast.AST,
    owner: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
) -> bool:
    current: ast.AST = node
    while current is not owner:
        parent: ast.AST | None = parents.get(current)
        if parent is None:
            return True
        if isinstance(parent, (ast.If, ast.While)) and isinstance(parent.test, ast.Constant):
            in_body: bool = current in parent.body
            if (in_body and not bool(parent.test.value)) or (
                not in_body and bool(parent.test.value)
            ):
                return True
        current = parent
    return False


def _keyword(*, call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _is_parametrize_call(
    *, expression: ast.expr, imports: dict[str, tuple[str, str | None]]
) -> bool:
    return (
        isinstance(expression, ast.Attribute)
        and expression.attr == _PARAMETRIZE_ATTRIBUTE
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == _PYTEST_MARK_ATTRIBUTE
        and isinstance(expression.value.value, ast.Name)
        and imports.get(expression.value.value.id) == (_PYTEST_MODULE_NAME, None)
    )


def _is_pytest_mark(
    *, expression: ast.expr, imports: dict[str, tuple[str, str | None]], mark: str
) -> bool:
    return (
        isinstance(expression, ast.Attribute)
        and expression.attr == mark
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == _PYTEST_MARK_ATTRIBUTE
        and isinstance(expression.value.value, ast.Name)
        and imports.get(expression.value.value.id) == (_PYTEST_MODULE_NAME, None)
    )


def _parameter_names(expression: ast.expr) -> tuple[str, ...]:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return tuple(name.strip() for name in expression.value.split(","))
    if isinstance(expression, (ast.List, ast.Tuple)):
        values: list[str] = []
        for item in expression.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return ()
            values.append(item.value)
        return tuple(values)
    return ()


def _module_names(*, path: Path, project_dir: Path) -> frozenset[str]:
    relative: Path = path.relative_to(project_dir.resolve()).with_suffix("")
    parts: tuple[str, ...] = relative.parts
    if parts and parts[-1] == _INIT_MODULE_NAME:
        parts = parts[:-1]
    names: set[str] = {".".join(parts)}
    for index in range(len(parts)):
        package_parts: tuple[str, ...] = parts[index:-1]
        package_root: Path = project_dir.joinpath(*parts[:index])
        if package_parts and all(
            (package_root.joinpath(*package_parts[:offset], "__init__.py")).is_file()
            for offset in range(1, len(package_parts) + 1)
        ):
            names.add(".".join(parts[index:]))
    return frozenset(names)


def _source_root(*, source_path: Path, project_dir: Path) -> Path:
    root: Path = project_dir.resolve()
    for parent in (source_path.parent, *source_path.parents):
        if parent == root:
            break
        if parent.name == _RULES_DIRECTORY_NAME:
            return parent
    return source_path.parent
