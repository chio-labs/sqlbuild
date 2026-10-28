"""Relation answers shared through the open run's relation metadata cache."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.relations._helpers.relation_metadata_context import (
    current_relation_metadata_cache,
)
from sqlbuild.adapter.relations.classes.relation_metadata_cache import RelationMetadataCache
from sqlbuild.adapter.relations.constants import RELATION_EXISTS_LOOKUP, RELATION_TYPE_LOOKUP
from sqlbuild.adapter.relations.types import SchemaListingScope


class RunRelationListings:
    """Schema listings and known relation states of the run open for an adapter, if any."""

    @staticmethod
    def schema_relation(
        *,
        adapter: Any,
        scope: SchemaListingScope,
        name: str,
        stored_name: str,
        read_listing: Callable[[], dict[str, RelationInfo]],
    ) -> tuple[bool, RelationInfo | None]:
        """Whether the run's schema listing answers ``name``, and the relation it lists."""

        cache: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
        if cache is None:
            return False, None
        return cache.schema_relation(
            scope=scope, name=name, stored_name=stored_name, read_listing=read_listing
        )

    @staticmethod
    def listed_relation(
        *, adapter: Any, scope: SchemaListingScope, name: str, stored_name: str
    ) -> tuple[bool, RelationInfo | None]:
        """Whether a current listing answers ``name``, and the relation it lists; never lists."""

        cache: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
        if cache is None:
            return False, None
        return cache.listed_relation(scope=scope, name=name, stored_name=stored_name)

    @staticmethod
    def refresh_schema_listing(
        *,
        adapter: Any,
        scope: SchemaListingScope,
        read_listing: Callable[[], dict[str, RelationInfo]],
    ) -> dict[str, RelationInfo]:
        """Read the schema's relations, keeping them for the run's later lookups."""

        cache: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
        if cache is None:
            return read_listing()
        return cache.refresh_schema_listing(scope=scope, read_listing=read_listing).relations

    @staticmethod
    def remember_absent(
        *, adapter: Any, relations: tuple[tuple[str | None, str | None, str], ...]
    ) -> None:
        """Answer later existence and type lookups of ``relations`` as absent until SQL runs."""

        cache: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
        if cache is None:
            return
        database: str | None
        schema: str | None
        name: str
        for database, schema, name in relations:
            cache.remember(
                kind=RELATION_EXISTS_LOOKUP,
                database=database,
                schema=schema,
                name=name,
                value=False,
            )
            cache.remember(
                kind=RELATION_TYPE_LOOKUP, database=database, schema=schema, name=name, value=None
            )
