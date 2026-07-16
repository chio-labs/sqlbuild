"""Source relation rendering implementation."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.spec.contracts.models import SourceEntry


def render_source_relation_impl(*, entry: SourceEntry, adapter: StrictAdapter | None = None) -> str:
    """Render a source as a SQL table factor."""

    if entry.expression is not None:
        if adapter is not None:
            return adapter.render_source_expression_relation(expression=entry.expression)
        return _render_source_expression_relation(expression=entry.expression)

    table_name: str = entry.table if entry.table is not None else entry.name
    if adapter is not None:
        rendered: str | None = adapter.render_qualified_name(
            database=entry.database,
            schema=entry.schema,
            name=table_name,
        )
        if rendered is not None:
            return rendered

    parts: list[str] = []
    if entry.database is not None:
        parts.append(entry.database)
    if entry.schema is not None:
        parts.append(entry.schema)
    parts.append(table_name)
    return ".".join(parts)


def _render_source_expression_relation(*, expression: str) -> str:
    stripped_expression: str = expression.strip().removesuffix(";").strip()
    if stripped_expression.startswith("("):
        return stripped_expression
    lowered: str = stripped_expression.lower()
    if lowered.startswith(("select", "with", "values")):
        return f"({stripped_expression})"
    return stripped_expression
