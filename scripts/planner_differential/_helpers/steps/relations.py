"""Split relation names the plan reports."""

from __future__ import annotations

_DEFAULT_SCHEMA: str = "main"


def schema_and_name(qualified_name: str) -> tuple[str, str]:
    """Return a `schema.name` or `database.schema.name` relation's schema and name."""

    parts: list[str] = qualified_name.split(".")
    return (parts[-2] if len(parts) > 1 else _DEFAULT_SCHEMA, parts[-1])
