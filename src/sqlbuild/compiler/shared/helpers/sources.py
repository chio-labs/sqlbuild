"""Shared source rendering helpers."""

from __future__ import annotations

from sqlbuild.spec.models.source import SourceEntry

_QUERY_EXPRESSION_PREFIXES: tuple[str, ...] = ("select", "with", "values")


def render_source_relation(entry: SourceEntry) -> str:
    """Render a source as a SQL table factor."""

    if entry.expression is not None:
        expression: str = entry.expression.strip().removesuffix(";").strip()
        if expression.startswith("("):
            return expression
        lowered: str = expression.lower()
        if lowered.startswith(_QUERY_EXPRESSION_PREFIXES):
            return f"({expression})"
        return expression

    parts: list[str] = []
    if entry.database is not None:
        parts.append(entry.database)
    if entry.schema is not None:
        parts.append(entry.schema)
    table_name: str = entry.table if entry.table is not None else entry.name
    parts.append(table_name)
    return ".".join(parts)
