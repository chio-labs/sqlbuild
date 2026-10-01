"""Invocation-local relation metadata cache state."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any

from sqlbuild.adapter.relations.classes.relation_metadata_cache import RelationMetadataCache

_ACTIVE_CACHE: ContextVar[tuple[Any, RelationMetadataCache] | None] = ContextVar(
    "sqlbuild_relation_metadata_cache", default=None
)


def current_relation_metadata_cache(*, adapter: Any) -> RelationMetadataCache | None:
    """Return the cache open for exactly this adapter, if any."""

    active: tuple[Any, RelationMetadataCache] | None = _ACTIVE_CACHE.get()
    if active is None or active[0] is not adapter:
        return None
    return active[1]


def activate_relation_metadata_cache(
    *, adapter: Any, cache: RelationMetadataCache
) -> Token[tuple[Any, RelationMetadataCache] | None]:
    """Make ``cache`` the open cache for ``adapter`` in this context."""

    return _ACTIVE_CACHE.set((adapter, cache))


def deactivate_relation_metadata_cache(
    token: Token[tuple[Any, RelationMetadataCache] | None],
) -> None:
    """Restore the cache that was open before ``activate_relation_metadata_cache``."""

    _ACTIVE_CACHE.reset(token)


def read_through_relation_metadata_cache[ValueT](
    *,
    adapter: Any,
    kind: str,
    database: str | None,
    schema: str | None,
    name: str,
    read: Callable[[], ValueT],
) -> ValueT:
    """Answer one lookup from the cache open for ``adapter``, or read it when none is open."""

    cache: RelationMetadataCache | None = current_relation_metadata_cache(adapter=adapter)
    if cache is None:
        return read()
    return cache.lookup(kind=kind, database=database, schema=schema, name=name, read=read)
