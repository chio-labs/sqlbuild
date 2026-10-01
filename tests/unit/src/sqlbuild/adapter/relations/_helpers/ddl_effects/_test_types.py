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


@dataclass(frozen=True)
class QualifiedNameKeyTestCase:
    """One adapter-supplied qualified name and its invalidation key, if parseable."""

    description: str
    qualified: str
    expected_key: str | None


@dataclass(frozen=True)
class AdversarialStatementTestCase:
    """Hostile SQL that statement scanners must still handle in bounded time."""

    description: str
    sql: str
    expected_max_seconds: float = 2.0
