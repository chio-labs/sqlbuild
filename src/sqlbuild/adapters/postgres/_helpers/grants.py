"""Read and replay PostgreSQL privileges onto a compatibility view."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.main.grants_for_columns import grants_for_columns
from sqlbuild.adapter.contract.models import RelationGrant


def postgres_relation_grants(
    *, relation_rows: list[tuple[Any, ...]], column_rows: list[tuple[Any, ...]]
) -> tuple[RelationGrant, ...]:
    """Decode aclexplode rows of a relation and of its columns."""

    return (
        *(
            RelationGrant(
                privilege=str(row[0]),
                grantee=None if row[1] is None else str(row[1]),
                grantable=bool(row[2]),
            )
            for row in relation_rows
        ),
        *(
            RelationGrant(
                privilege=str(row[1]),
                grantee=None if row[2] is None else str(row[2]),
                column=str(row[0]),
                grantable=bool(row[3]),
            )
            for row in column_rows
        ),
    )


def render_postgres_grants(
    *,
    grants: tuple[RelationGrant, ...],
    destination: str,
    columns: tuple[str, ...],
    render_identifier: Callable[[str], str],
) -> tuple[str, ...]:
    """Render table and exposed column privileges as grants on ``destination``."""

    return tuple(
        f"GRANT {grant.privilege}"
        + ("" if grant.column is None else f" ({render_identifier(grant.column)})")
        + f" ON {destination} TO "
        + ("PUBLIC" if grant.grantee is None else render_identifier(grant.grantee))
        + (" WITH GRANT OPTION" if grant.grantable else "")
        for grant in grants_for_columns(grants=grants, columns=columns)
    )


def render_postgres_revokes(
    *,
    grants: tuple[RelationGrant, ...],
    destination: str,
    render_identifier: Callable[[str], str],
) -> tuple[str, ...]:
    """Render grants to remove from ``destination``, grant option included."""

    return tuple(
        f"REVOKE {grant.privilege}"
        + ("" if grant.column is None else f" ({render_identifier(grant.column)})")
        + f" ON {destination} FROM "
        + ("PUBLIC" if grant.grantee is None else render_identifier(grant.grantee))
        for grant in grants
    )
