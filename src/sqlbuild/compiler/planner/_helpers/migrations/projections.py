"""Formatting-insensitive query shapes used to prove that a change is only a column rename."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlbuild.compiler.planner._helpers.migrations.fingerprint import strip_ast_formatting
from sqlbuild.compiler.planner.models import QueryProjection, QueryShape
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_GENERIC_DIALECT: str = "generic"
_SELECT_KEY: str = "select"
_EXPRESSIONS_KEY: str = "expressions"
_ALIAS_KEY: str = "alias"
_THIS_KEY: str = "this"
_COLUMN_KEY: str = "column"
_NAME_KEY: str = "name"
_QUOTED_KEY: str = "quoted"
_TABLE_KEY: str = "table"
_LITERAL_KEY: str = "literal"
_LITERAL_TYPE_KEY: str = "literal_type"
_NUMBER_LITERAL: str = "number"
_GROUP_BY_KEY: str = "group_by"
_ORDER_BY_KEY: str = "order_by"
_DISTINCT_ON_KEY: str = "distinct_on"
_ALIAS_SCOPED_KEYS: tuple[str, ...] = (_ORDER_BY_KEY, "qualify")


def parse_query_shape(*, query_sql: str, dialect: str | None) -> QueryShape | None:
    """Return the named top-level projections of one plain SELECT, or None when unknowable."""

    polyglot: Any = import_polyglot_sql()
    try:
        parsed: Any = polyglot.parse_one(query_sql, dialect=dialect or _GENERIC_DIALECT).to_dict()
    except polyglot.PolyglotError:
        return None
    root: Any = strip_ast_formatting(parsed)
    if not isinstance(root, dict) or set(root) != {_SELECT_KEY}:
        return None
    select: Any = root[_SELECT_KEY]
    if not isinstance(select, dict) or not isinstance(select.get(_EXPRESSIONS_KEY), list):
        return None
    projections: list[QueryProjection] = []
    expression: Any
    for expression in select[_EXPRESSIONS_KEY]:
        projection: QueryProjection | None = _projection(expression)
        if projection is None:
            return None
        projections.append(projection)
    if len({projection.key for projection in projections}) != len(projections):
        return None
    canonical: dict[str, Any] = _canonical(select)
    body: dict[str, Any] = {
        key: value
        for key, value in canonical.items()
        if key != _EXPRESSIONS_KEY and key not in _ALIAS_SCOPED_KEYS
    }
    return QueryShape(
        projections=tuple(projections),
        body=_encode(body),
        alias_clauses=_encode({key: canonical.get(key) for key in _ALIAS_SCOPED_KEYS}),
        positional=_has_positional_reference(canonical),
    )


def renames_explain_change(
    *, previous: QueryShape, current: QueryShape, renames: Mapping[str, str]
) -> bool:
    """Return whether renaming output columns, matched by name, is the whole query change."""

    if not renames or previous.body != current.body:
        return False
    lowered: dict[str, str] = {old.lower(): new.lower() for old, new in renames.items()}
    renamed_previous: dict[str, str] = {
        lowered.get(item.key, item.key): item.expression for item in previous.projections
    }
    current_projections: dict[str, str] = {
        item.key: item.expression for item in current.projections
    }
    if (
        len(renamed_previous) != len(previous.projections)
        or renamed_previous != current_projections
    ):
        return False
    reordered: bool = tuple(lowered.get(item.key, item.key) for item in previous.projections) != (
        tuple(item.key for item in current.projections)
    )
    if reordered and (previous.positional or current.positional):
        return False
    restored: Any = _substitute_alias_references(
        node=json.loads(current.alias_clauses),
        names={new: old for old, new in lowered.items()},
    )
    return _encode(restored) == previous.alias_clauses


def _substitute_alias_references(*, node: Any, names: Mapping[str, str]) -> Any:
    """Rename unqualified references to output aliases, leaving nested queries untouched."""

    if isinstance(node, list):
        return [_substitute_alias_references(node=value, names=names) for value in node]
    if not isinstance(node, dict) or _SELECT_KEY in node:
        return node
    column: Any = node.get(_COLUMN_KEY)
    if isinstance(column, dict) and column.get(_TABLE_KEY) is None:
        identifier: Any = column.get(_NAME_KEY)
        name: str | None = _identifier_name(identifier)
        if name is not None and identifier.get(_QUOTED_KEY) is False and name in names:
            return {
                **node,
                _COLUMN_KEY: {**column, _NAME_KEY: {**identifier, _NAME_KEY: names[name]}},
            }
    return {
        key: _substitute_alias_references(node=value, names=names) for key, value in node.items()
    }


def _has_positional_reference(select: Mapping[str, Any]) -> bool:
    """Return whether grouping, ordering, or DISTINCT ON refer to output columns by position."""

    items: list[Any] = [*_clause_items(select.get(_GROUP_BY_KEY))]
    items.extend(
        item.get(_THIS_KEY) if isinstance(item, dict) else item
        for item in _clause_items(select.get(_ORDER_BY_KEY))
    )
    items.extend(_clause_items(select.get(_DISTINCT_ON_KEY)))
    return any(
        isinstance(item, dict)
        and isinstance(item.get(_LITERAL_KEY), dict)
        and item[_LITERAL_KEY].get(_LITERAL_TYPE_KEY) == _NUMBER_LITERAL
        for item in items
    )


def _clause_items(clause: Any) -> list[Any]:
    if isinstance(clause, list):
        return clause
    if isinstance(clause, dict) and isinstance(clause.get(_EXPRESSIONS_KEY), list):
        return list(clause[_EXPRESSIONS_KEY])
    return []


def _projection(expression: Any) -> QueryProjection | None:
    if not isinstance(expression, dict) or len(expression) != 1:
        return None
    if _ALIAS_KEY in expression:
        alias: Any = expression[_ALIAS_KEY]
        name: str | None = (
            _identifier_name(alias.get(_ALIAS_KEY)) if isinstance(alias, dict) else None
        )
        body: Any = alias.get(_THIS_KEY) if isinstance(alias, dict) else None
        if name is None or body is None:
            return None
        return QueryProjection(
            name=name, expression=_encode(_canonical(body)), references=_references(body)
        )
    if _COLUMN_KEY in expression:
        column: Any = expression[_COLUMN_KEY]
        name = _identifier_name(column.get(_NAME_KEY)) if isinstance(column, dict) else None
        if name is None:
            return None
        return QueryProjection(
            name=name,
            expression=_encode(_canonical(expression)),
            references=_references(expression),
        )
    return None


def _identifier_name(identifier: Any) -> str | None:
    if not isinstance(identifier, dict) or not isinstance(identifier.get(_NAME_KEY), str):
        return None
    return str(identifier[_NAME_KEY])


def _references(node: Any) -> frozenset[str]:
    found: set[str] = set()
    pending: list[Any] = [node]
    while pending:
        current: Any = pending.pop()
        if isinstance(current, list):
            pending.extend(current)
            continue
        if not isinstance(current, dict):
            continue
        column: Any = current.get(_COLUMN_KEY)
        if isinstance(column, dict):
            name: str | None = _identifier_name(column.get(_NAME_KEY))
            if name is not None:
                found.add(name.lower())
        pending.extend(current.values())
    return frozenset(found)


def _canonical(node: Any) -> Any:
    """Lower-case unquoted identifiers so letter case alone never looks like a change."""

    if isinstance(node, list):
        return [_canonical(value) for value in node]
    if not isinstance(node, dict):
        return node
    canonical: dict[str, Any] = {key: _canonical(value) for key, value in node.items()}
    if isinstance(canonical.get(_NAME_KEY), str) and canonical.get(_QUOTED_KEY) is False:
        canonical[_NAME_KEY] = str(canonical[_NAME_KEY]).lower()
    return canonical


def _encode(node: Any) -> str:
    return json.dumps(node, sort_keys=True, separators=(",", ":"), default=str)
