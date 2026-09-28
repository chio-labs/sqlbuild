"""Relation-name extraction and project-relation matching for hard-coded name checks."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

from sqlbuild.compiler.references.models import ProjectRelation, ProjectRelationIndex, RelationName
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_GENERIC_DIALECT: str = "generic"
_TABLE_KEYS: frozenset[str] = frozenset({"name", "schema", "catalog", "alias", "hints"})
_CTE_LIST_KEY: str = "ctes"
_CTE_ALIAS_KEY: str = "alias"
_CREATE_TABLE_KEY: str = "create_table"
_TEMPORARY_KEY: str = "temporary"
_QUALIFIER_SEPARATOR: str = "."
_SCHEMA_QUALIFIED_PART_COUNT: int = 2


def extract_relation_names_impl(
    *, sql: str, dialect: str | None
) -> tuple[tuple[RelationName, ...], frozenset[str]] | None:
    """Return relations named in ``sql`` and temporary tables it creates, or None if unparseable."""

    polyglot: Any = import_polyglot_sql()
    try:
        statements: list[Any] = polyglot.parse(sql, dialect=dialect or _GENERIC_DIALECT)
    except polyglot.PolyglotError:
        return None
    names: dict[RelationName, None] = {}
    temporary: set[str] = set()
    for statement in statements:
        tree: object = statement.to_dict()
        cte_names: frozenset[str] = frozenset(_cte_names(tree))
        temporary.update(_temporary_table_names(tree))
        for relation in _table_names(tree):
            if relation.schema is None and relation.database is None:
                if relation.name.casefold() in cte_names:
                    continue
            names[relation] = None
    return tuple(names), frozenset(temporary)


def match_project_relation_impl(
    *,
    index: ProjectRelationIndex,
    relation: RelationName,
    default_database: str | None,
    default_schema: str | None,
) -> ProjectRelation | None:
    """Return the project relation ``relation`` names, resolving missing qualifiers."""

    schema: str | None = relation.schema if relation.schema is not None else default_schema
    database: str | None = relation.database if relation.database is not None else default_database
    for candidate in index.relations:
        target: RelationName = candidate.relation
        if target.name.casefold() != relation.name.casefold():
            continue
        if not _parts_compatible(left=schema, right=target.schema):
            continue
        if not _parts_compatible(left=database, right=target.database):
            continue
        return candidate
    return None


def _parts_compatible(*, left: str | None, right: str | None) -> bool:
    return left is None or right is None or left.casefold() == right.casefold()


def _walk(node: object) -> Iterator[dict[str, object]]:
    pending: list[object] = [node]
    while pending:
        current: object = pending.pop()
        if isinstance(current, dict):
            mapping: dict[str, object] = cast(dict[str, object], current)
            yield mapping
            pending.extend(mapping.values())
        elif isinstance(current, list | tuple):
            pending.extend(current)


def _identifier(value: object) -> str | None:
    if isinstance(value, dict):
        name: object = cast(dict[str, object], value).get("name")
        return name if isinstance(name, str) else None
    return None


def _table_names(tree: object) -> Iterator[RelationName]:
    for node in _walk(tree):
        if not _TABLE_KEYS.issubset(node.keys()):
            continue
        name: str | None = _identifier(node.get("name"))
        if name is None:
            continue
        schema: str | None = _identifier(node.get("schema"))
        database: str | None = _identifier(node.get("catalog"))
        if schema is None and database is None and _QUALIFIER_SEPARATOR in name:
            parts: list[str] = name.split(_QUALIFIER_SEPARATOR)
            name = parts[-1]
            schema = parts[-2]
            database = parts[-3] if len(parts) > _SCHEMA_QUALIFIED_PART_COUNT else None
        yield RelationName(name=name, schema=schema, database=database)


def _cte_names(tree: object) -> Iterator[str]:
    for node in _walk(tree):
        ctes: object = node.get(_CTE_LIST_KEY)
        if not isinstance(ctes, list):
            continue
        for cte in ctes:
            alias: str | None = (
                _identifier(cast(dict[str, object], cte).get(_CTE_ALIAS_KEY))
                if isinstance(cte, dict)
                else None
            )
            if alias is not None:
                yield alias.casefold()


def _temporary_table_names(tree: object) -> Iterator[str]:
    for node in _walk(tree):
        create: object = node.get(_CREATE_TABLE_KEY)
        if not isinstance(create, dict):
            continue
        create_table: dict[str, object] = cast(dict[str, object], create)
        if create_table.get(_TEMPORARY_KEY) is not True:
            continue
        table: object = create_table.get("name")
        name: str | None = (
            _identifier(cast(dict[str, object], table).get("name"))
            if isinstance(table, dict)
            else None
        )
        if name is not None:
            yield name.casefold()
