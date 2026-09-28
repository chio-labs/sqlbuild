"""Read and replay BigQuery table IAM bindings onto a compatibility view."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import RelationGrant

_ROLE_COLUMN: int = 0
_GRANTEE_COLUMN: int = 1


def bigquery_relation_grants(rows: list[tuple[Any, ...]]) -> tuple[RelationGrant, ...]:
    """Decode OBJECT_PRIVILEGES role bindings."""

    return tuple(
        RelationGrant(privilege=str(row[_ROLE_COLUMN]), grantee=str(row[_GRANTEE_COLUMN]))
        for row in rows
    )


def render_bigquery_view_grants(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render role bindings as DCL grants on ``destination``."""

    return tuple(
        f"GRANT `{grant.privilege.replace('`', '')}` ON VIEW {destination} "
        f'TO "{(grant.grantee or "").replace(chr(34), "")}"'
        for grant in grants
    )


def render_bigquery_view_revokes(
    *, grants: tuple[RelationGrant, ...], destination: str
) -> tuple[str, ...]:
    """Render role bindings to remove from ``destination``."""

    return tuple(
        f"REVOKE `{grant.privilege.replace('`', '')}` ON VIEW {destination} "
        f'FROM "{(grant.grantee or "").replace(chr(34), "")}"'
        for grant in grants
    )


def render_bigquery_view_move(
    *, origin: str, destination: str, definition: str, grants: tuple[str, ...]
) -> tuple[str, ...]:
    """Re-create a view under a new name with its grants, since BigQuery cannot rename views."""

    return (f"CREATE VIEW {destination} AS {definition}", *grants, f"DROP VIEW {origin}")
