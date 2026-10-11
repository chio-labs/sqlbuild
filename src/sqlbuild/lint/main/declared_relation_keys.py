"""Declared unique keys of project relations, for ranking determinism proofs."""

from __future__ import annotations

from collections.abc import Iterable

import sqlbuild._native as _native
from sqlbuild.lint.constants import RELATION_KIND_SEED, RELATION_KIND_SOURCE
from sqlbuild.lint.types import RelationKeyRow, RelationKeys
from sqlbuild.spec.contracts.models import SchemaSeedEntry, SourceEntry


def declared_relation_keys(
    *,
    model_rows: Iterable[RelationKeyRow],
    seeds: Iterable[SchemaSeedEntry],
    sources: Iterable[SourceEntry],
) -> RelationKeys:
    """Keys that prove one row per key, from model key rows and seed and source entries."""

    rows: list[RelationKeyRow] = [
        *model_rows,
        *(_native.relation_key_row(RELATION_KIND_SEED, seed.name, {}, seed) for seed in seeds),
        *(
            _native.relation_key_row(RELATION_KIND_SOURCE, source.name, {}, source)
            for source in sources
        ),
    ]
    keys: RelationKeys = {}
    for identity, found in _native.declared_relation_keys(rows).items():
        keys[identity] = tuple(map(tuple, found))
    return keys
