"""Public relation lookup batching entrypoint."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup


def build_relation_lookup(
    *,
    adapter: StrictAdapter,
    connection: Any,
    locations: tuple[tuple[str | None, str | None, str], ...],
) -> RelationLookup:
    """Gather relations for all locations with one list_relations call per database."""

    schemas_by_database: dict[str | None, set[str]] = defaultdict(set)
    schema_wildcard_names_by_database: dict[str | None, set[str]] = defaultdict(set)
    for database, schema, name in locations:
        if schema is None:
            schema_wildcard_names_by_database[database].add(name)
            continue
        schemas_by_database[database].add(schema)
    relations_by_key: dict[tuple[str | None, str | None, str], RelationInfo] = {}
    for database, schemas in schemas_by_database.items():
        relations: tuple[RelationInfo, ...] = adapter.list_relations(
            connection=connection,
            database=database,
            schemas=tuple(sorted(schemas)),
            names=None,
        )
        for relation in relations:
            relations_by_key[
                RelationLookup.key(
                    database=relation.database,
                    schema=relation.schema,
                    name=relation.name,
                )
            ] = relation
    for database, names in schema_wildcard_names_by_database.items():
        relations = adapter.list_relations(
            connection=connection,
            database=database,
            schemas=None,
            names=tuple(sorted(names)),
        )
        for relation in relations:
            relations_by_key[
                RelationLookup.key(
                    database=relation.database,
                    schema=relation.schema,
                    name=relation.name,
                )
            ] = relation
            relations_by_key[
                RelationLookup.key(
                    database=relation.database,
                    schema=None,
                    name=relation.name,
                )
            ] = relation
    return RelationLookup(relations_by_key=relations_by_key)
