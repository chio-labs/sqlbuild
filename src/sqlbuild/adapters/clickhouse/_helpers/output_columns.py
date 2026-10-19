"""Detect output columns ClickHouse named after their table alias."""

from __future__ import annotations

from sqlbuild.adapters.clickhouse.constants import QUALIFIER_SEPARATOR


def alias_qualified_columns(
    *, actual: tuple[str, ...], expected: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    """Pairs of an ``alias.column`` name ClickHouse produced and the ``column`` analysis expects."""

    wanted: frozenset[str] = frozenset(expected) - frozenset(actual)
    pairs: tuple[tuple[str, str], ...] = tuple(
        (name, name.rpartition(QUALIFIER_SEPARATOR)[2]) for name in actual
    )
    return tuple(
        (produced, column) for produced, column in pairs if produced != column and column in wanted
    )
