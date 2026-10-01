from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatementMetadataEffectTestCase:
    """One executed statement and the cached relation names it may have changed."""

    description: str
    sql: str
    expected_relation_names: frozenset[str]
    expected_invalidates_all: bool
    expected_ends_transaction: bool = False
