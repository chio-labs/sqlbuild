"""Structural analysis helpers for execution observability rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from fensu import ImportAliasFact, ImportFact, RuleContext

from scripts.fensu_policy.constants import (
    EVENT_EXPORTER_INTEGRATION_PATHS,
    EVENT_EXPORTER_PUBLIC_PATH,
    EVENT_EXPORTER_RUNTIME_PREFIX,
    KNOWN_DRIVER_MODULE_PREFIXES,
    RAW_CURSOR_FACTORY_NAME,
    RAW_DRIVER_FACTORY_NAMES,
    RAW_STATEMENT_METHOD_NAMES,
)


@dataclass(frozen=True)
class _LexicalState:
    driver_modules: frozenset[str] = frozenset()
    driver_factories: frozenset[str] = frozenset()
    driver_types: frozenset[str] = frozenset()
    raw_expressions: frozenset[str] = frozenset()


def import_source_parts(*, imported: ImportFact, alias: ImportAliasFact) -> tuple[str, ...]:
    """Return the complete imported path represented by one alias fact."""

    return imported.module_parts + alias.imported_parts


def imported_reference_matches(
    *,
    ctx: RuleContext,
    reference_parts: tuple[str, ...],
    symbol: str,
    source_modules: tuple[tuple[str, ...], ...],
) -> bool:
    """Return whether a complete reference resolves to an imported owner symbol."""

    for imported in ctx.facts.references().imports:
        for alias in imported.aliases:
            if (
                imported.from_import
                and imported.module_parts in source_modules
                and alias.imported_name == symbol
                and reference_parts == (alias.bound_name,)
            ):
                return True
            source_parts: tuple[str, ...] = import_source_parts(imported=imported, alias=alias)
            if source_parts not in source_modules:
                continue
            expected: tuple[str, ...] = source_parts + (symbol,)
            if reference_parts == expected or (
                reference_parts[:1] == (alias.bound_name,)
                and source_parts + reference_parts[1:] == expected
            ):
                return True
    return False


def expression_reference_parts(expression: ast.expr) -> tuple[str, ...] | None:
    """Return complete name/attribute parts for a decorator or call expression."""

    if isinstance(expression, ast.Name):
        return (expression.id,)
    if isinstance(expression, ast.Attribute):
        owner: tuple[str, ...] | None = expression_reference_parts(expression.value)
        return None if owner is None else owner + (expression.attr,)
    return None


def raw_execution_calls(*, tree: ast.Module, ctx: RuleContext) -> tuple[ast.Call, ...]:
    """Return calls whose receiver has statically proven known-driver provenance."""

    del ctx
    calls, _ = _analyze_block(statements=tuple(tree.body), state=_LexicalState())
    return calls


def _analyze_block(
    *, statements: tuple[ast.stmt, ...], state: _LexicalState
) -> tuple[tuple[ast.Call, ...], _LexicalState]:
    calls: list[ast.Call] = []
    current: _LexicalState = state
    for statement in statements:
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            current = _state_after_import(statement=statement, state=current)
            continue
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_state: _LexicalState = _function_state(function=statement, state=current)
            nested_calls, _ = _analyze_block(statements=tuple(statement.body), state=function_state)
            calls.extend(nested_calls)
            continue
        if isinstance(statement, ast.ClassDef):
            nested_calls, _ = _analyze_block(statements=tuple(statement.body), state=current)
            calls.extend(nested_calls)
            continue
        calls.extend(_execution_calls(node=statement, state=current))
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            current = _state_after_assignment(statement=statement, state=current)
        elif isinstance(statement, (ast.With, ast.AsyncWith)):
            with_state: _LexicalState = current
            for item in statement.items:
                if item.optional_vars is not None:
                    with_state = _state_after_target(
                        target=item.optional_vars,
                        is_raw=_lexical_expression_is_raw(
                            expression=item.context_expr, state=with_state
                        ),
                        state=with_state,
                    )
            nested_calls, current = _analyze_block(
                statements=tuple(statement.body), state=with_state
            )
            calls.extend(nested_calls)
        elif isinstance(statement, ast.If):
            body_calls, _ = _analyze_block(statements=tuple(statement.body), state=current)
            else_calls, _ = _analyze_block(statements=tuple(statement.orelse), state=current)
            calls.extend(body_calls)
            calls.extend(else_calls)
        elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
            body_calls, _ = _analyze_block(statements=tuple(statement.body), state=current)
            else_calls, _ = _analyze_block(statements=tuple(statement.orelse), state=current)
            calls.extend(body_calls)
            calls.extend(else_calls)
        elif isinstance(statement, ast.Try):
            body_calls, _ = _analyze_block(statements=tuple(statement.body), state=current)
            calls.extend(body_calls)
            for handler in statement.handlers:
                handler_calls, _ = _analyze_block(statements=tuple(handler.body), state=current)
                calls.extend(handler_calls)
            else_calls, _ = _analyze_block(statements=tuple(statement.orelse), state=current)
            final_calls, _ = _analyze_block(statements=tuple(statement.finalbody), state=current)
            calls.extend(else_calls)
            calls.extend(final_calls)
    return tuple(calls), current


def _state_after_import(
    *, statement: ast.Import | ast.ImportFrom, state: _LexicalState
) -> _LexicalState:
    modules: set[str] = set(state.driver_modules)
    factories: set[str] = set(state.driver_factories)
    types: set[str] = set(state.driver_types)
    module_parts: tuple[str, ...] = ()
    if isinstance(statement, ast.ImportFrom) and statement.module is not None:
        module_parts = tuple(statement.module.split("."))
    for alias in statement.names:
        source_parts: tuple[str, ...] = (
            tuple(alias.name.split("."))
            if isinstance(statement, ast.Import)
            else module_parts + tuple(alias.name.split("."))
        )
        matching_prefixes: tuple[tuple[str, ...], ...] = tuple(
            prefix
            for prefix in KNOWN_DRIVER_MODULE_PREFIXES
            if source_parts[: len(prefix)] == prefix
        )
        if not matching_prefixes:
            continue
        bound_name: str = alias.asname or (
            source_parts[0] if isinstance(statement, ast.Import) else alias.name
        )
        if isinstance(statement, ast.ImportFrom) and alias.name in RAW_DRIVER_FACTORY_NAMES:
            factories.add(bound_name)
        elif source_parts in matching_prefixes:
            modules.add(bound_name)
        else:
            types.add(bound_name)
    return _LexicalState(
        driver_modules=frozenset(modules),
        driver_factories=frozenset(factories),
        driver_types=frozenset(types),
        raw_expressions=state.raw_expressions,
    )


def _function_state(
    *, function: ast.FunctionDef | ast.AsyncFunctionDef, state: _LexicalState
) -> _LexicalState:
    current: _LexicalState = state
    arguments: tuple[ast.arg, ...] = (
        tuple(function.args.posonlyargs)
        + tuple(function.args.args)
        + tuple(function.args.kwonlyargs)
    )
    if function.args.vararg is not None:
        arguments += (function.args.vararg,)
    if function.args.kwarg is not None:
        arguments += (function.args.kwarg,)
    for argument in arguments:
        is_raw: bool = argument.annotation is not None and _lexical_annotation_is_driver(
            annotation=argument.annotation, state=current
        )
        current = _state_after_target(
            target=ast.Name(id=argument.arg), is_raw=is_raw, state=current
        )
    return current


def _state_after_assignment(
    *, statement: ast.Assign | ast.AnnAssign, state: _LexicalState
) -> _LexicalState:
    if isinstance(statement, ast.Assign):
        is_raw: bool = _lexical_expression_is_raw(expression=statement.value, state=state)
        current: _LexicalState = state
        for target in statement.targets:
            current = _state_after_target(target=target, is_raw=is_raw, state=current)
        return current
    is_raw = (
        statement.value is not None
        and _lexical_expression_is_raw(expression=statement.value, state=state)
    ) or _lexical_annotation_is_driver(annotation=statement.annotation, state=state)
    return _state_after_target(target=statement.target, is_raw=is_raw, state=state)


def _state_after_target(*, target: ast.expr, is_raw: bool, state: _LexicalState) -> _LexicalState:
    expressions: set[str] = set(state.raw_expressions)
    targets: tuple[ast.expr, ...] = (
        tuple(target.elts) if isinstance(target, (ast.Tuple, ast.List)) else (target,)
    )
    for item in targets:
        if not isinstance(item, (ast.Name, ast.Attribute)):
            continue
        key: str = _expression_key(item)
        expressions.discard(key)
        if is_raw:
            expressions.add(key)
    return _LexicalState(
        driver_modules=state.driver_modules,
        driver_factories=state.driver_factories,
        driver_types=state.driver_types,
        raw_expressions=frozenset(expressions),
    )


def _execution_calls(*, node: ast.AST, state: _LexicalState) -> tuple[ast.Call, ...]:
    calls: list[ast.Call] = []
    pending: list[ast.AST] = [node]
    while pending:
        current: ast.AST = pending.pop()
        if current is not node and isinstance(current, ast.stmt):
            continue
        if current is not node and isinstance(
            current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
        ):
            continue
        if (
            isinstance(current, ast.Call)
            and isinstance(current.func, ast.Attribute)
            and current.func.attr in RAW_STATEMENT_METHOD_NAMES
            and _lexical_expression_is_raw(expression=current.func.value, state=state)
        ):
            calls.append(current)
        pending.extend(ast.iter_child_nodes(current))
    return tuple(calls)


def _lexical_annotation_is_driver(*, annotation: ast.expr, state: _LexicalState) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id in state.driver_types
    if isinstance(annotation, ast.Attribute):
        return _expression_root_name(annotation) in state.driver_modules
    if isinstance(annotation, ast.Subscript):
        return any(
            _lexical_annotation_is_driver(annotation=child, state=state)
            for child in ast.iter_child_nodes(annotation)
            if isinstance(child, ast.expr)
        )
    if isinstance(annotation, ast.BinOp):
        return _lexical_annotation_is_driver(
            annotation=annotation.left, state=state
        ) or _lexical_annotation_is_driver(annotation=annotation.right, state=state)
    return False


def _lexical_expression_is_raw(*, expression: ast.expr, state: _LexicalState) -> bool:
    if _expression_key(expression) in state.raw_expressions:
        return True
    if isinstance(expression, ast.Name):
        return expression.id in state.driver_modules
    if not isinstance(expression, ast.Call):
        return False
    function: ast.expr = expression.func
    if isinstance(function, ast.Name):
        return function.id in state.driver_factories
    if not isinstance(function, ast.Attribute):
        return False
    if (
        _expression_root_name(function.value) in state.driver_modules
        and function.attr in RAW_DRIVER_FACTORY_NAMES
    ):
        return True
    return function.attr == RAW_CURSOR_FACTORY_NAME and _lexical_expression_is_raw(
        expression=function.value, state=state
    )


def private_exporter_imports_are_allowed(*, path: str) -> bool:
    """Return whether a module is a runtime owner or exact integration seam."""

    return (
        path.startswith(EVENT_EXPORTER_RUNTIME_PREFIX)
        or path == EVENT_EXPORTER_PUBLIC_PATH
        or path in EVENT_EXPORTER_INTEGRATION_PATHS
    )


def ast_nodes(root: ast.AST) -> tuple[ast.AST, ...]:
    """Return a deterministic recursive AST traversal without untracked filesystem access."""

    nodes: list[ast.AST] = [root]
    pending: list[ast.AST] = [root]
    while pending:
        current: ast.AST = pending.pop()
        children: tuple[ast.AST, ...] = tuple(ast.iter_child_nodes(current))
        nodes.extend(children)
        pending.extend(children)
    return tuple(nodes)


def _expression_key(expression: ast.expr) -> str:
    return ast.unparse(expression)


def _expression_root_name(expression: ast.expr) -> str | None:
    while isinstance(expression, ast.Attribute):
        expression = expression.value
    return expression.id if isinstance(expression, ast.Name) else None
