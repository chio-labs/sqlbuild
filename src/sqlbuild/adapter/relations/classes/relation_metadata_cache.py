"""Invocation-scoped relation existence and column metadata shared by build workers."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import cast

from sqlbuild.adapter.relations._helpers.ddl_effects import (
    qualified_relation_name_key,
    relation_name_key,
    statement_metadata_effect,
)
from sqlbuild.adapter.relations.models import StatementMetadataEffect
from sqlbuild.adapter.relations.types import RelationCacheKey, RelationCacheVersion


class RelationMetadataCache:
    """Serve repeated identical metadata lookups until SQL may have changed the relation."""

    def __init__(self, *, transactional_ddl: bool) -> None:
        self._transactional_ddl: bool = transactional_ddl
        self._lock: threading.Lock = threading.Lock()
        self._entries: dict[RelationCacheKey, object] = {}
        self._name_versions: dict[str, int] = {}
        self._global_version: int = 0
        self._pending_names: dict[int, set[str]] = {}
        self._pending_all: set[int] = set()

    def lookup[ValueT](
        self,
        *,
        kind: str,
        database: str | None,
        schema: str | None,
        name: str,
        read: Callable[[], ValueT],
    ) -> ValueT:
        """Return the cached answer for this exact lookup, reading it on a miss."""

        return cast(ValueT, self._lookup(key=(kind, database, schema, name), read=read))

    def invalidate_relations(self, *, qualified_names: tuple[str, ...]) -> None:
        """Evict relations changed outside SQL statements, such as by a warehouse copy job."""

        keys: tuple[str | None, ...] = tuple(map(qualified_relation_name_key, qualified_names))
        names: frozenset[str] = frozenset(key for key in keys if key is not None)
        with self._lock:
            if None in keys:
                self._invalidate_all()
                return
            self._invalidate_names(names=names)

    def observe_statement(self, *, sql: str) -> None:
        """Invalidate entries the finished statement ``sql`` may have changed."""

        effect: StatementMetadataEffect = statement_metadata_effect(sql)
        thread_id: int = threading.get_ident()
        with self._lock:
            if effect.ends_transaction and self._transactional_ddl:
                names: set[str] = self._pending_names.pop(thread_id, set())
                if thread_id in self._pending_all:
                    self._pending_all.discard(thread_id)
                    self._invalidate_all()
                else:
                    self._invalidate_names(names=frozenset(names))
                return
            if effect.invalidates_all:
                if self._transactional_ddl:
                    self._pending_all.add(thread_id)
                self._invalidate_all()
                return
            if effect.relation_names:
                if self._transactional_ddl:
                    self._pending_names.setdefault(thread_id, set()).update(effect.relation_names)
                self._invalidate_names(names=effect.relation_names)

    def _lookup(self, *, key: RelationCacheKey, read: Callable[[], object]) -> object:
        name_key: str = relation_name_key(key[3])
        with self._lock:
            if key in self._entries:
                return self._entries[key]
            version: RelationCacheVersion = self._version(name_key=name_key)
        value: object = read()
        with self._lock:
            if self._version(name_key=name_key) == version:
                self._entries[key] = value
        return value

    def _version(self, *, name_key: str) -> RelationCacheVersion:
        return self._global_version, self._name_versions.get(name_key, 0)

    def _invalidate_names(self, *, names: frozenset[str]) -> None:
        if not names:
            return
        name: str
        for name in names:
            self._name_versions[name] = self._name_versions.get(name, 0) + 1
        stale: list[RelationCacheKey] = [
            key for key in self._entries if relation_name_key(key[3]) in names
        ]
        key: RelationCacheKey
        for key in stale:
            del self._entries[key]

    def _invalidate_all(self) -> None:
        self._global_version += 1
        self._entries.clear()
