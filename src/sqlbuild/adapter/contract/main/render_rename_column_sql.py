"""Shared ALTER TABLE ... RENAME COLUMN rendering for adapters that support it."""

from __future__ import annotations


def render_alter_rename_column_sql(
    *, destination: str, old_identifier: str, new_identifier: str
) -> str:
    """Render one in-place column rename from already-quoted identifiers."""

    return f"ALTER TABLE {destination} RENAME COLUMN {old_identifier} TO {new_identifier}"
