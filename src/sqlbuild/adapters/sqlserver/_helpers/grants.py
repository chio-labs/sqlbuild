"""Read and replay SQL Server object and column permissions onto a compatibility view."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.main.grants_for_columns import grants_for_columns
from sqlbuild.adapter.contract.models import RelationGrant

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
_COLUMN_PERMISSIONS: frozenset[str] = frozenset({"REFERENCES", "SELECT", "UPDATE"})
_STATES: dict[str, tuple[bool, bool]] = {
    "GRANT": (False, False),
    "GRANT_WITH_GRANT_OPTION": (False, True),
    "DENY": (True, False),
}
_STATE_COLUMN: int = 0
_PERMISSION_COLUMN: int = 1
_GRANTEE_COLUMN: int = 2
_COLUMN_NAME_COLUMN: int = 3


def sqlserver_relation_grants(rows: list[tuple[Any, ...]]) -> tuple[RelationGrant, ...]:
    """Decode object and column grants and denies that also apply to a view."""

    grants: list[RelationGrant] = []
    row: tuple[Any, ...]
    for row in rows:
        permission: str = str(row[_PERMISSION_COLUMN]).upper()
        state: tuple[bool, bool] | None = _STATES.get(str(row[_STATE_COLUMN]).upper())
        column: str | None = (
            None if row[_COLUMN_NAME_COLUMN] is None else str(row[_COLUMN_NAME_COLUMN])
        )
        allowed: frozenset[str] = _VIEW_PERMISSIONS if column is None else _COLUMN_PERMISSIONS
        if state is None or permission not in allowed:
            continue
        grants.append(
            RelationGrant(
                privilege=permission,
                grantee=str(row[_GRANTEE_COLUMN]),
                column=column,
                grantable=state[1],
                denied=state[0],
            )
        )
    return tuple(grants)


def render_sqlserver_view_grants(
    *, grants: tuple[RelationGrant, ...], destination: str, columns: tuple[str, ...]
) -> tuple[str, ...]:
    """Render object permissions, then permissions on columns the view exposes."""

    return tuple(
        ("DENY" if grant.denied else "GRANT")
        + f" {grant.privilege} ON OBJECT::{destination}"
        + ("" if grant.column is None else " ([" + grant.column.replace("]", "]]") + "])")
        + " TO ["
        + (grant.grantee or "").replace("]", "]]")
        + "]"
        + (" WITH GRANT OPTION" if grant.grantable else "")
        for grant in grants_for_columns(grants=grants, columns=columns)
    )


def render_sqlserver_view_revokes(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render grants or denies to remove from ``destination``, cascading grant options."""

    return tuple(
        f"REVOKE {grant.privilege} ON OBJECT::{destination}"
        + ("" if grant.column is None else " ([" + grant.column.replace("]", "]]") + "])")
        + " FROM ["
        + (grant.grantee or "").replace("]", "]]")
        + "]"
        + (" CASCADE" if grant.grantable else "")
        for grant in grants
    )
