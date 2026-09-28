"""Render BigQuery table IAM bindings replayed onto a compatibility view."""

from __future__ import annotations

from typing import Any

_ROLE_COLUMN: int = 0
_GRANTEE_COLUMN: int = 1


def render_bigquery_view_grants(
    *, rows: list[tuple[Any, ...]], destination: str
) -> tuple[str, ...]:
    """Replay OBJECT_PRIVILEGES role bindings as DCL grants on the view."""

    return tuple(
        f"GRANT `{str(row[_ROLE_COLUMN]).replace('`', '')}` ON VIEW {destination} "
        f'TO "{str(row[_GRANTEE_COLUMN]).replace(chr(34), "")}"'
        for row in rows
    )


def render_bigquery_view_move(*, origin: str, destination: str, definition: str) -> tuple[str, ...]:
    """Re-create a view under a new name, since BigQuery cannot rename views, then drop it."""

    return (f"CREATE VIEW {destination} AS {definition}", f"DROP VIEW {origin}")
