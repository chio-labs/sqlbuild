"""Scope one relation metadata cache to a build invocation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import Token
from typing import Any

from sqlbuild.adapter.relations._helpers.relation_metadata_context import (
    activate_relation_metadata_cache,
    current_relation_metadata_cache,
    deactivate_relation_metadata_cache,
)
from sqlbuild.adapter.relations.classes.relation_metadata_cache import RelationMetadataCache
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle


@contextmanager
def relation_metadata_cache_scope(*, adapter: Any) -> Iterator[RelationMetadataCache]:
    """Share relation metadata reads until the scope exits; nested scopes reuse the open cache."""

    existing: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
    if existing is not None:
        yield existing
        return
    cache: RelationMetadataCache = RelationMetadataCache(
        transactional_ddl=bool(adapter.supports_transactional_ddl())
    )
    token: Token[tuple[Any, RelationMetadataCache] | None] = activate_relation_metadata_cache(
        adapter=adapter, cache=cache
    )
    try:
        with StatementLifecycle.listener_scope(cache.observe_statement):
            yield cache
    finally:
        _ = deactivate_relation_metadata_cache(token)
