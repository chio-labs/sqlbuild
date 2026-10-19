"""Read one relation's live type through the open relation metadata cache."""

from __future__ import annotations

from functools import partial
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations._helpers.relation_metadata_context import (
    read_through_relation_metadata_cache,
)
from sqlbuild.adapter.relations.constants import RELATION_TYPE_LOOKUP
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type


def cached_relation_type(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str | None, name: str
) -> RelationType | None:
    """The warehouse type of the relation at this location, or `None` when none exists."""

    return read_through_relation_metadata_cache(
        adapter=adapter,
        kind=RELATION_TYPE_LOOKUP,
        database=database,
        schema=schema,
        name=name,
        read=partial(
            _relation_type,
            adapter=adapter,
            connection=connection,
            database=database,
            schema=schema,
            name=name,
        ),
    )


def _relation_type(
    *, adapter: BaseAdapter, connection: Any, database: str | None, schema: str | None, name: str
) -> RelationType | None:
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection,
        database=database,
        schemas=None if schema is None else (schema,),
        names=(name,),
    )
    wanted: tuple[str | None, str | None, str] = RelationLookup.key(schema=schema, name=name)
    for relation in relations:
        found: tuple[str | None, str | None, str] = RelationLookup.key(
            schema=None if schema is None else relation.schema, name=relation.name
        )
        if found == wanted:
            return normalize_relation_type(relation.relation_type)
    return None
