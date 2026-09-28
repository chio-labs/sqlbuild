"""Formatting-insensitive query shapes used to prove that a change is only a column rename."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlbuild.compiler.planner._helpers.migrations.fingerprint import strip_ast_formatting
from sqlbuild.compiler.planner.constants import REF_INPUT_FUNCTION, SOURCE_INPUT_FUNCTION
from sqlbuild.compiler.planner.models import QueryProjection, QueryShape
from sqlbuild.compiler.planner.types import InputColumns
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
_FROM_KEY: str = "from"
_JOINS_KEY: str = "joins"
_WITH_KEY: str = "with"
_ON_KEY: str = "on"
_LATERAL_VIEWS_KEY: str = "lateral_views"
_CTES_KEY: str = "ctes"
_COLUMNS_KEY: str = "columns"
_COLUMN_ALIASES_KEY: str = "column_aliases"
_FUNCTION_KEY: str = "function"
_ARGS_KEY: str = "args"
_SUBQUERY_KEY: str = "subquery"
_RELATION_FUNCTIONS: frozenset[str] = frozenset({SOURCE_INPUT_FUNCTION, REF_INPUT_FUNCTION})
_UNSCANNED_CLAUSE_KEYS: frozenset[str] = frozenset(
    {_EXPRESSIONS_KEY, _WITH_KEY, _FROM_KEY, _JOINS_KEY}
)


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
    inputs: tuple[tuple[tuple[str, str], ...], frozenset[str]] | None = _select_inputs(canonical)
    return QueryShape(
        projections=tuple(projections),
        body=_encode(body),
        alias_clauses=_encode({key: canonical.get(key) for key in _ALIAS_SCOPED_KEYS}),
        positional=_has_positional_reference(canonical),
        input_relations=inputs[0] if inputs is not None else None,
        local_input_columns=inputs[1] if inputs is not None else frozenset(),
        clause_references=_unqualified_references(
            [value for key, value in canonical.items() if key not in _UNSCANNED_CLAUSE_KEYS]
            + [join.get(_ON_KEY) for join in _dicts(canonical.get(_JOINS_KEY))]
        ),
    )


def renames_explain_change(
    *,
    previous: QueryShape,
    current: QueryShape,
    renames: Mapping[str, str],
    input_columns: InputColumns,
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
    if not all(
        _binding_proven(
            previous=previous,
            current=current,
            origin=origin,
            destination=destination,
            input_columns=input_columns,
        )
        for origin, destination in lowered.items()
    ):
        return False
    restored: Any = _substitute_alias_references(
        node=json.loads(current.alias_clauses),
        names={new: old for old, new in lowered.items()},
    )
    return _encode(restored) == previous.alias_clauses


def _binding_proven(
    *,
    previous: QueryShape,
    current: QueryShape,
    origin: str,
    destination: str,
    input_columns: InputColumns,
) -> bool:
    """Return whether references to a renamed column provably bind the same in both queries."""

    referenced: frozenset[str] = (
        previous.clause_references
        | current.clause_references
        | _other_projection_references(shape=previous, excluded=origin)
        | _other_projection_references(shape=current, excluded=destination)
    )
    if origin not in referenced and destination not in referenced:
        return True
    inputs: frozenset[str] | None = _known_input_columns(shape=current, input_columns=input_columns)
    if inputs is None or destination in inputs:
        return False
    if origin in inputs:
        return any(item.key == origin and item.passthrough for item in previous.projections)
    return origin not in (
        current.clause_references | _other_projection_references(shape=current, excluded="")
    )


def _other_projection_references(*, shape: QueryShape, excluded: str) -> frozenset[str]:
    return frozenset().union(
        *(item.references for item in shape.projections if item.key != excluded)
    )


def _known_input_columns(
    *, shape: QueryShape, input_columns: InputColumns
) -> frozenset[str] | None:
    if shape.input_relations is None:
        return None
    known: set[str] = set(shape.local_input_columns)
    kind: str
    name: str
    for kind, name in shape.input_relations:
        columns: frozenset[str] | None = input_columns(kind, name)
        if columns is None:
            return None
        known.update(columns)
    return frozenset(known)


def _select_inputs(
    select: Mapping[str, Any],
) -> tuple[tuple[tuple[str, str], ...], frozenset[str]] | None:
    """Return a SELECT's referenced relations and derived-table columns, or None when unknown."""

    if _dicts(select.get(_LATERAL_VIEWS_KEY)):
        return None
    ctes: dict[str, frozenset[str] | None] = _cte_columns(select.get(_WITH_KEY))
    items: list[Any] = list(_clause_items(select.get(_FROM_KEY)))
    items.extend(join.get(_THIS_KEY) for join in _dicts(select.get(_JOINS_KEY)))
    relations: list[tuple[str, str]] = []
    local: set[str] = set()
    item: Any
    for item in items:
        resolved: tuple[tuple[str, str] | None, frozenset[str] | None] = _input_item(
            item=item, ctes=ctes
        )
        if resolved[0] is not None:
            relations.append(resolved[0])
        elif resolved[1] is not None:
            local.update(resolved[1])
        else:
            return None
    return tuple(relations), frozenset(local)


def _input_item(
    *, item: Any, ctes: Mapping[str, frozenset[str] | None]
) -> tuple[tuple[str, str] | None, frozenset[str] | None]:
    """Resolve one FROM or JOIN item to a relation name or to its known columns."""

    if not isinstance(item, dict) or len(item) != 1:
        return None, None
    if _ALIAS_KEY in item:
        alias: Any = item[_ALIAS_KEY]
        if not isinstance(alias, dict):
            return None, None
        renamed: tuple[str, ...] = _identifier_names(alias.get(_COLUMN_ALIASES_KEY))
        inner: tuple[tuple[str, str] | None, frozenset[str] | None] = _input_item(
            item=alias.get(_THIS_KEY), ctes=ctes
        )
        if renamed and (inner[0] is not None or inner[1] is not None):
            return None, frozenset(renamed)
        return inner
    function: Any = item.get(_FUNCTION_KEY)
    if isinstance(function, dict):
        args: Any = function.get(_ARGS_KEY)
        kind: str = str(function.get(_NAME_KEY, "")).lower()
        if (
            kind not in _RELATION_FUNCTIONS
            or not isinstance(args, list)
            or len(args) != 1
            or not isinstance(args[0], dict)
            or not isinstance(args[0].get(_COLUMN_KEY), dict)
        ):
            return None, None
        relation: str | None = _identifier_name(args[0][_COLUMN_KEY].get(_NAME_KEY))
        return (None if relation is None else (kind, relation)), None
    table: Any = item.get(_TABLE_KEY)
    if isinstance(table, dict):
        name: str | None = _identifier_name(table.get(_NAME_KEY))
        if name is None or table.get("schema") is not None or table.get("catalog") is not None:
            return None, None
        return None, ctes.get(name)
    subquery: Any = item.get(_SUBQUERY_KEY)
    if isinstance(subquery, dict):
        return None, _output_names(subquery.get(_THIS_KEY))
    return None, None


def _cte_columns(with_clause: Any) -> dict[str, frozenset[str] | None]:
    if not isinstance(with_clause, dict):
        return {}
    columns: dict[str, frozenset[str] | None] = {}
    cte: dict[str, Any]
    for cte in _dicts(with_clause.get(_CTES_KEY)):
        name: str | None = _identifier_name(cte.get(_ALIAS_KEY))
        if name is None:
            continue
        declared: tuple[str, ...] = _identifier_names(cte.get(_COLUMNS_KEY))
        columns[name] = frozenset(declared) if declared else _output_names(cte.get(_THIS_KEY))
    return columns


def _output_names(query: Any) -> frozenset[str] | None:
    """Return the lower-cased output names of a plain SELECT, or None when any is unknown."""

    if not isinstance(query, dict) or set(query) != {_SELECT_KEY}:
        return None
    expressions: Any = query[_SELECT_KEY].get(_EXPRESSIONS_KEY)
    if not isinstance(expressions, list):
        return None
    projections: list[QueryProjection | None] = [_projection(value) for value in expressions]
    if any(projection is None for projection in projections):
        return None
    return frozenset(projection.key for projection in projections if projection is not None)


def _identifier_names(identifiers: Any) -> tuple[str, ...]:
    return tuple(
        name.lower()
        for identifier in (identifiers if isinstance(identifiers, list) else [])
        if (name := _identifier_name(identifier)) is not None
    )


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _unqualified_references(node: Any) -> frozenset[str]:
    """Return lower-cased names of unqualified column references anywhere under node."""

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
        if isinstance(column, dict) and column.get(_TABLE_KEY) is None:
            name: str | None = _identifier_name(column.get(_NAME_KEY))
            if name is not None:
                found.add(name.lower())
        pending.extend(current.values())
    return frozenset(found)


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
            name=name,
            expression=_encode(_canonical(body)),
            references=_references(body),
            passthrough=_is_bare_column(node=body, name=name),
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
            passthrough=_is_bare_column(node=expression, name=name),
        )
    return None


def _is_bare_column(*, node: Any, name: str) -> bool:
    """Return whether node is an unqualified reference to a column with the given name."""

    column: Any = node.get(_COLUMN_KEY) if isinstance(node, dict) else None
    if not isinstance(column, dict) or column.get(_TABLE_KEY) is not None:
        return False
    referenced: str | None = _identifier_name(column.get(_NAME_KEY))
    return referenced is not None and referenced.lower() == name.lower()


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
