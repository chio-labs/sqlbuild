"""Evict relations an adapter changed without a SQL statement from the open cache."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.relations._helpers.relation_metadata_context import (
    current_relation_metadata_cache,
)
from sqlbuild.adapter.relations.classes.relation_metadata_cache import RelationMetadataCache


def invalidate_cached_relations(*, adapter: Any, qualified_names: tuple[str, ...]) -> None:
    """Make the next lookup of each named relation read the warehouse again."""

    cache: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
    if cache is not None:
        cache.invalidate_relations(qualified_names=qualified_names)
