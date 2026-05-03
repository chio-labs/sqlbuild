"""Relation naming helpers shared across executor packages."""

from __future__ import annotations


def build_qualified_name(
    *,
    database: str | None,
    schema: str | None,
    name: str,
) -> str:
    """Build a dot-separated qualified relation name from parts."""

    parts: list[str] = []
    if database is not None:
        parts.append(database)
    if schema is not None:
        parts.append(schema)
    parts.append(name)
    return ".".join(parts)
