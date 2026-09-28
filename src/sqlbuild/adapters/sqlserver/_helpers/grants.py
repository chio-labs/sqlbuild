"""Render SQL Server object permissions replayed onto a compatibility view."""

from __future__ import annotations

from typing import Any

_VIEW_PERMISSIONS: frozenset[str] = frozenset(
    {
        "ALTER",
        "CONTROL",
        "DELETE",
        "INSERT",
        "REFERENCES",
        "SELECT",
        "TAKE OWNERSHIP",
        "UPDATE",
        "VIEW CHANGE TRACKING",
        "VIEW DEFINITION",
    }
)
_STATE_TEMPLATES: dict[str, str] = {
    "GRANT": "GRANT {permission} ON OBJECT::{destination} TO {grantee}",
    "GRANT_WITH_GRANT_OPTION": (
        "GRANT {permission} ON OBJECT::{destination} TO {grantee} WITH GRANT OPTION"
    ),
    "DENY": "DENY {permission} ON OBJECT::{destination} TO {grantee}",
}
_STATE_COLUMN: int = 0
_PERMISSION_COLUMN: int = 1
_GRANTEE_COLUMN: int = 2


def render_sqlserver_view_grants(
    *, rows: list[tuple[Any, ...]], destination: str
) -> tuple[str, ...]:
    """Replay object-level grants and denies that also apply to a view."""

    statements: list[str] = []
    row: tuple[Any, ...]
    for row in rows:
        permission: str = str(row[_PERMISSION_COLUMN]).upper()
        template: str | None = _STATE_TEMPLATES.get(str(row[_STATE_COLUMN]).upper())
        if template is None or permission not in _VIEW_PERMISSIONS:
            continue
        grantee: str = "[" + str(row[_GRANTEE_COLUMN]).replace("]", "]]") + "]"
        statements.append(
            template.format(permission=permission, destination=destination, grantee=grantee)
        )
    return tuple(statements)
