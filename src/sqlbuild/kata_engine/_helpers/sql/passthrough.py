"""Shared shape-only passthrough classification."""

from __future__ import annotations

import re
from typing import Any, cast

from sqlbuild.kata_engine._helpers.sql.ast import kind, name_value, payload, top_level_ctes
from sqlbuild.kata_engine.constants import (
    AST_ALIAS_KIND,
    AST_COLUMN_KIND,
    AST_FUNCTION_KIND,
    AST_SELECT_KIND,
    AST_STAR_KIND,
    AST_TABLE_KIND,
    DEPENDENCY_FUNCTIONS,
)

_REFERENCE_PATTERN: re.Pattern[str] = re.compile(r"__(?:ref|source)\s*\(", re.IGNORECASE)
_FORBIDDEN_KINDS: frozenset[str] = frozenset(
    {"aggfunc", "case", "group", "join", "window", "windowfunc"}
)


def is_passthrough_ast(*, ast: Any, source: str) -> bool:
    """Return whether a model has the narrow import-and-project passthrough shape."""

    ctes: tuple[Any, ...] = top_level_ctes(ast)
    if len(ctes) != 1 or len(_REFERENCE_PATTERN.findall(source)) != 1:
        return False
    import_body: Any = ctes[0][1]
    if not is_dependency_import(node=import_body) or not is_plain_projection(
        select=import_body, allow_star=True
    ):
        return False
    terminal_source: dict[str, object] | None = _sole_from_expression(select=ast)
    if terminal_source is None or AST_TABLE_KIND not in terminal_source:
        return False
    table_payload: object = terminal_source.get(AST_TABLE_KIND)
    if not isinstance(table_payload, dict):
        return False
    table_name: str = name_value(cast(dict[str, object], table_payload).get("name"))
    return table_name == str(ctes[0][0]) and is_plain_projection(select=ast, allow_star=True)


def is_dependency_import(*, node: Any) -> bool:
    """Return whether one select is a projection from exactly one dependency macro."""

    source: dict[str, object] | None = _sole_from_expression(select=node)
    if source is None or AST_FUNCTION_KIND not in source:
        return False
    function_payload: object = source.get(AST_FUNCTION_KIND)
    if not isinstance(function_payload, dict):
        return False
    function_name: object = cast(dict[str, object], function_payload).get("name")
    data: dict[str, object] = payload(node)
    has_forbidden_shape: bool = any(
        (
            data.get("group_by"),
            data.get("having"),
            data.get("joins"),
            data.get("qualify"),
            data.get("with"),
        )
    )
    return (
        str(function_name).lower() in DEPENDENCY_FUNCTIONS
        and not has_forbidden_shape
        and _has_plain_expressions(select=node, allow_star=True)
    )


def is_plain_projection(*, select: Any, allow_star: bool) -> bool:
    """Return whether one select contains only a direct column projection."""

    if kind(select) != AST_SELECT_KIND:
        return False
    data: dict[str, object] = payload(select)
    if data.get("where_clause") is not None or data.get("having") is not None:
        return False
    if data.get("qualify") is not None or data.get("group_by") is not None:
        return False
    if data.get("joins"):
        return False
    for node in select.walk():
        if kind(node) in _FORBIDDEN_KINDS:
            return False
    return _has_plain_expressions(select=select, allow_star=allow_star)


def _has_plain_expressions(*, select: Any, allow_star: bool) -> bool:
    expressions: tuple[Any, ...] = tuple(select.expressions)
    if not expressions:
        return False
    if len(expressions) == 1 and kind(expressions[0]) == AST_STAR_KIND:
        return allow_star
    for expression in expressions:
        expression_kind: str = kind(expression)
        if expression_kind == AST_COLUMN_KIND:
            continue
        if expression_kind == AST_ALIAS_KIND:
            children: tuple[Any, ...] = tuple(expression.children())
            if children and kind(children[0]) == AST_COLUMN_KIND:
                continue
        return False
    return True


def _sole_from_expression(*, select: Any) -> dict[str, object] | None:
    data: dict[str, object] = payload(select)
    from_payload: object = data.get("from")
    if not isinstance(from_payload, dict):
        return None
    raw_expressions: object = cast(dict[str, object], from_payload).get("expressions")
    if not isinstance(raw_expressions, list) or len(raw_expressions) != 1:
        return None
    expression: object = raw_expressions[0]
    return cast(dict[str, object], expression) if isinstance(expression, dict) else None
