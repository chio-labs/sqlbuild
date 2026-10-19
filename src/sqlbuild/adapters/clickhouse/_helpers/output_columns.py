"""Column names in ClickHouse query outputs and table key expressions."""

from __future__ import annotations

from sqlbuild.adapters.clickhouse.constants import KEY_IDENTIFIER_PATTERN, QUALIFIER_SEPARATOR


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


def key_identifiers(key_expressions: tuple[str, ...]) -> frozenset[str]:
    """The column names that appear in a table's key expressions."""

    matches: list[tuple[str, str]] = KEY_IDENTIFIER_PATTERN.findall(" ".join(key_expressions))
    return frozenset(quoted or bare for quoted, bare in matches)
